import { PrivyClient } from "@privy-io/node";
import { createViemAccount } from "@privy-io/node/viem";
import * as hl from "@nktkas/hyperliquid";
import { createPublicClient, createWalletClient, encodeFunctionData, http, parseUnits } from "viem";
import { arbitrum } from "viem/chains";

const command = process.argv[2];
const ARBITRUM_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";
const HYPERLIQUID_BRIDGE2 = "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7";
const ERC20_ABI = [
  {
    type: "function",
    name: "transfer",
    stateMutability: "nonpayable",
    inputs: [
      { name: "to", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
];

function readStdin() {
  return new Promise((resolve, reject) => {
    let input = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      input += chunk;
    });
    process.stdin.on("end", () => {
      try {
        resolve(input ? JSON.parse(input) : {});
      } catch (error) {
        reject(error);
      }
    });
  });
}

function requireEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function formatError(error) {
  const parts = [];
  let current = error;
  while (current) {
    parts.push(current?.stack || current?.message || String(current));
    current = current.cause;
  }
  return parts.join("\nCaused by: ");
}

function transportFor(network) {
  return new hl.HttpTransport({ isTestnet: network !== "prodnet" });
}

function privyClient() {
  return new PrivyClient({
    appId: requireEnv("PRIVY_APP_ID"),
    appSecret: requireEnv("PRIVY_APP_SECRET"),
  });
}

async function createEthereumWallet(privy) {
  const wallets = privy.wallets();
  if (typeof wallets.createWallet === "function") {
    return wallets.createWallet({ chain_type: "ethereum" });
  }
  return wallets.create({ chain_type: "ethereum" });
}

async function withRetries(label, action, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await action();
    } catch (error) {
      lastError = error;
      if (attempt === attempts) break;
      await new Promise((resolve) => setTimeout(resolve, attempt * 1500));
    }
  }
  const message = lastError?.message || String(lastError);
  throw new Error(`${label} failed after ${attempts} attempts: ${message}`);
}

function viemAccount(privy, wallet) {
  const account = createViemAccount(privy, {
    walletId: wallet.id,
    address: wallet.address,
  });

  const signTypedData = account.signTypedData.bind(account);
  account.signTypedData = async (typedData) => {
    const { EIP712Domain, ...types } = typedData.types || {};
    return signTypedData({ ...typedData, types });
  };

  return account;
}

async function assetContext(transport, asset) {
  const infoClient = new hl.InfoClient({ transport });
  const [meta, contexts] = await infoClient.metaAndAssetCtxs();
  const index = meta.universe.findIndex((item) => item.name === asset);
  if (index < 0) throw new Error(`${asset} not found in Hyperliquid metadata`);
  return {
    index,
    meta: meta.universe[index],
    context: contexts[index],
  };
}

function trimNumber(value) {
  return String(value).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function formatSize(value, szDecimals) {
  return trimNumber(Number(value).toFixed(szDecimals));
}

function formatPrice(value, szDecimals) {
  const maxDecimals = Math.max(0, 6 - Number(szDecimals || 0));
  const fixed = Number(value).toFixed(maxDecimals);
  const trimmed = trimNumber(fixed);
  const significant = Number(trimmed).toPrecision(5);
  return trimNumber(Number(significant).toFixed(maxDecimals));
}

function extractOrderId(response) {
  const statuses = response?.response?.data?.statuses;
  const status = Array.isArray(statuses) ? statuses[0] : null;
  const resting = status?.resting || status?.filled;
  return resting?.oid ? String(resting.oid) : null;
}

async function setupAgent(input) {
  const privy = privyClient();
  const network = input.network || "testnet";
  const transport = transportFor(network);
  const agentName = input.agentName || "HyperClaude";

  const masterWallet = input.masterWalletId && input.masterWalletAddress
    ? { id: input.masterWalletId, address: input.masterWalletAddress }
    : await withRetries("create master wallet", () => createEthereumWallet(privy));
  const agentWallet = input.agentWalletId && input.agentWalletAddress
    ? { id: input.agentWalletId, address: input.agentWalletAddress }
    : await withRetries("create agent wallet", () => createEthereumWallet(privy));

  const masterClient = new hl.ExchangeClient({
    transport,
    wallet: viemAccount(privy, masterWallet),
  });

  let registered = false;
  let registerResponse = null;
  try {
    registerResponse = await masterClient.approveAgent({
      agentAddress: agentWallet.address,
      agentName,
    });
    registered = true;
  } catch (error) {
    const message = String(error?.message || error);
    if (message.toLowerCase().includes("already")) {
      registered = true;
    } else if (message.toLowerCase().includes("must deposit")) {
      registerResponse = {
        error: message,
        action_required: "Deposit to the Privy master wallet on Hyperliquid, then retry setup.",
      };
    } else {
      throw error;
    }
  }

  return {
    network,
    agentName,
    registered,
    masterWallet,
    agentWallet,
    registerResponse,
  };
}

async function executePlan(input) {
  const privy = privyClient();
  const transport = transportFor(input.network || "testnet");
  const plan = input.plan;
  if (!plan) throw new Error("plan is required");

  const { index, meta } = await assetContext(transport, plan.asset);
  const szDecimals = Number(meta.szDecimals || 5);
  const size = formatSize(plan.size, szDecimals);
  const isBuy = plan.side === "long";
  const closingIsBuy = !isBuy;

  const client = new hl.ExchangeClient({
    transport,
    wallet: viemAccount(privy, {
      id: input.agentWalletId,
      address: input.agentWalletAddress,
    }),
  });

  const entryPrice = formatPrice(plan.entryPrice, szDecimals);
  const entry = await client.order({
    grouping: "na",
    orders: [
      {
        a: index,
        b: isBuy,
        s: size,
        p: entryPrice,
        r: false,
        t: { limit: { tif: plan.entryType === "market" ? "Ioc" : "Gtc" } },
      },
    ],
  });

  const stopTrigger = formatPrice(plan.stopLoss, szDecimals);
  const takeProfitTrigger = formatPrice(plan.takeProfit, szDecimals);
  const stopLoss = await client.order({
    grouping: "na",
    orders: [
      {
        a: index,
        b: closingIsBuy,
        s: size,
        p: stopTrigger,
        r: true,
        t: {
          trigger: {
            isMarket: true,
            tpsl: "sl",
            triggerPx: stopTrigger,
          },
        },
      },
    ],
  });
  const takeProfit = await client.order({
    grouping: "na",
    orders: [
      {
        a: index,
        b: closingIsBuy,
        s: size,
        p: takeProfitTrigger,
        r: true,
        t: {
          trigger: {
            isMarket: true,
            tpsl: "tp",
            triggerPx: takeProfitTrigger,
          },
        },
      },
    ],
  });

  return {
    entry,
    stopLoss,
    takeProfit,
    entryOrderId: extractOrderId(entry),
    stopOrderId: extractOrderId(stopLoss),
    takeProfitOrderId: extractOrderId(takeProfit),
  };
}

async function walletState(input) {
  const transport = transportFor(input.network || "testnet");
  const infoClient = new hl.InfoClient({ transport });
  const user = input.masterWalletAddress || input.agentWalletAddress;
  if (!user) throw new Error("masterWalletAddress or agentWalletAddress is required");
  const state = await infoClient.clearinghouseState({ user });
  const openOrders = await infoClient.openOrders({ user });
  return {
    account_address: user,
    agent_address: input.agentWalletAddress || null,
    collateral_usdc: Number(state?.marginSummary?.accountValue || 0),
    total_margin_used_usdc: Number(state?.marginSummary?.totalMarginUsed || 0),
    withdrawable_usdc: Number(state?.withdrawable || 0),
    open_positions: state?.assetPositions || [],
    open_orders: openOrders || [],
    raw: state,
  };
}

async function depositMaster(input) {
  if ((input.network || "testnet") !== "prodnet") {
    throw new Error("Integrated master deposits are only configured for prodnet.");
  }
  const amount = Number(input.amountUsdc || 0);
  if (!Number.isFinite(amount) || amount < 5) {
    throw new Error("Hyperliquid Bridge2 deposits require at least 5 USDC.");
  }
  if (!input.masterWalletId || !input.masterWalletAddress) {
    throw new Error("masterWalletId and masterWalletAddress are required");
  }

  const privy = privyClient();
  const account = viemAccount(privy, {
    id: input.masterWalletId,
    address: input.masterWalletAddress,
  });
  const walletClient = createWalletClient({
    account,
    chain: arbitrum,
    transport: http(),
  });
  const publicClient = createPublicClient({
    chain: arbitrum,
    transport: http(),
  });
  const value = parseUnits(String(amount), 6);
  const hash = await walletClient.sendTransaction({
    account,
    chain: arbitrum,
    to: ARBITRUM_USDC,
    data: encodeFunctionData({
      abi: ERC20_ABI,
      functionName: "transfer",
      args: [HYPERLIQUID_BRIDGE2, value],
    }),
  });
  const receipt = await publicClient.waitForTransactionReceipt({ hash });
  return {
    network: "prodnet",
    protocol: "Arbitrum One USDC -> Hyperliquid Bridge2",
    bridgeAddress: HYPERLIQUID_BRIDGE2,
    usdcAddress: ARBITRUM_USDC,
    amountUsdc: amount,
    hash,
    status: receipt.status,
    blockNumber: receipt.blockNumber.toString(),
  };
}

try {
  const input = await readStdin();
  let output;
  if (command === "setup-agent") output = await setupAgent(input);
  else if (command === "execute-plan") output = await executePlan(input);
  else if (command === "wallet-state") output = await walletState(input);
  else if (command === "deposit-master") output = await depositMaster(input);
  else throw new Error(`Unknown command: ${command}`);
  process.stdout.write(JSON.stringify(output));
} catch (error) {
  process.stderr.write(formatError(error));
  process.exit(1);
}
