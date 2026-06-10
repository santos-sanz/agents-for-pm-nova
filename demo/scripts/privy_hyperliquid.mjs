import { PrivyClient } from "@privy-io/node";
import { createViemAccount } from "@privy-io/node/viem";
import * as hl from "@nktkas/hyperliquid";

const command = process.argv[2];
const ARBITRUM_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";
const HYPERLIQUID_BRIDGE2 = "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7";

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
  const leverage = Math.max(1, Math.min(Number(plan.leverage || 1), Number(meta.maxLeverage || 50)));
  const leverageUpdate = await client.updateLeverage({
    asset: index,
    isCross: true,
    leverage,
  });

  const rawEntryPrice =
    plan.entryType === "market"
      ? Number(plan.entryPrice) * (isBuy ? 1.005 : 0.995)
      : Number(plan.entryPrice);
  const entryPrice = formatPrice(rawEntryPrice, szDecimals);
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

  const stopLoss = plan.stopLoss
    ? await client.order({
        grouping: "na",
        orders: [
          {
            a: index,
            b: closingIsBuy,
            s: size,
            p: formatPrice(plan.stopLoss, szDecimals),
            r: true,
            t: {
              trigger: {
                isMarket: true,
                tpsl: "sl",
                triggerPx: formatPrice(plan.stopLoss, szDecimals),
              },
            },
          },
        ],
      })
    : null;
  const takeProfit = plan.takeProfit
    ? await client.order({
        grouping: "na",
        orders: [
          {
            a: index,
            b: closingIsBuy,
            s: size,
            p: formatPrice(plan.takeProfit, szDecimals),
            r: true,
            t: {
              trigger: {
                isMarket: true,
                tpsl: "tp",
                triggerPx: formatPrice(plan.takeProfit, szDecimals),
              },
            },
          },
        ],
      })
    : null;

  return {
    entry,
    stopLoss,
    takeProfit,
    entryOrderId: extractOrderId(entry),
    stopOrderId: stopLoss ? extractOrderId(stopLoss) : null,
    takeProfitOrderId: takeProfit ? extractOrderId(takeProfit) : null,
    leverageUpdate,
  };
}

async function placeProtectionOrder(client, index, szDecimals, size, closingIsBuy, price, kind) {
  if (!price) return null;
  const triggerPx = formatPrice(price, szDecimals);
  return client.order({
    grouping: "na",
    orders: [
      {
        a: index,
        b: closingIsBuy,
        s: size,
        p: triggerPx,
        r: true,
        t: {
          trigger: {
            isMarket: true,
            tpsl: kind,
            triggerPx,
          },
        },
      },
    ],
  });
}

function protectionOrderKind(order, side, referencePrice) {
  const orderType = String(order?.orderType || "").toLowerCase();
  if (orderType.includes("take profit")) return "tp";
  if (orderType.includes("stop")) return "sl";
  const tpsl = order?.t?.trigger?.tpsl || order?.trigger?.tpsl || order?.tpsl;
  if (tpsl === "tp" || tpsl === "sl") return tpsl;
  const price = Number(order?.triggerPx || order?.limitPx || order?.price || order?.px || 0);
  const reference = Number(referencePrice || 0);
  if (!price || !reference) return null;
  if (side === "long") return price > reference ? "tp" : "sl";
  if (side === "short") return price < reference ? "tp" : "sl";
  return null;
}

async function cancelExistingProtectionOrders(
  client,
  infoClient,
  user,
  asset,
  index,
  kinds,
  side,
  referencePrice,
) {
  if (!kinds.size) return null;
  const openOrders = await infoClient.openOrders({ user });
  const cancels = (openOrders || [])
    .filter(
      (order) =>
        order?.coin === asset &&
        order?.reduceOnly !== false &&
        kinds.has(protectionOrderKind(order, side, referencePrice)),
    )
    .map((order) => Number(order.oid || order.orderId || 0))
    .filter((oid) => Number.isSafeInteger(oid) && oid > 0)
    .map((oid) => ({ a: index, o: oid }));
  if (!cancels.length) return null;
  return client.cancel({ cancels });
}

async function setProtection(input) {
  const privy = privyClient();
  const transport = transportFor(input.network || "testnet");
  const { index, meta, context } = await assetContext(transport, input.asset);
  const szDecimals = Number(meta.szDecimals || 5);
  const size = formatSize(input.size, szDecimals);
  const closingIsBuy = input.side === "short";
  const removeTakeProfit = Boolean(input.removeTakeProfit);
  const removeStopLoss = Boolean(input.removeStopLoss);
  if (!input.takeProfit && !input.stopLoss && !removeTakeProfit && !removeStopLoss) {
    throw new Error("takeProfit, stopLoss, removeTakeProfit, or removeStopLoss is required");
  }

  const client = new hl.ExchangeClient({
    transport,
    wallet: viemAccount(privy, {
      id: input.agentWalletId,
      address: input.agentWalletAddress,
    }),
  });
  const infoClient = new hl.InfoClient({ transport });
  const replacementKinds = new Set();
  if (input.takeProfit || removeTakeProfit) replacementKinds.add("tp");
  if (input.stopLoss || removeStopLoss) replacementKinds.add("sl");
  const cancelled = await cancelExistingProtectionOrders(
    client,
    infoClient,
    input.masterWalletAddress || input.agentWalletAddress,
    input.asset,
    index,
    replacementKinds,
    input.side,
    Number(context?.markPx || 0),
  );
  const stopLoss = await placeProtectionOrder(
    client,
    index,
    szDecimals,
    size,
    closingIsBuy,
    input.stopLoss,
    "sl",
  );
  const takeProfit = await placeProtectionOrder(
    client,
    index,
    szDecimals,
    size,
    closingIsBuy,
    input.takeProfit,
    "tp",
  );
  return {
    cancelled,
    stopLoss,
    takeProfit,
    stopOrderId: stopLoss ? extractOrderId(stopLoss) : null,
    takeProfitOrderId: takeProfit ? extractOrderId(takeProfit) : null,
  };
}

async function setLeverage(input) {
  const privy = privyClient();
  const transport = transportFor(input.network || "testnet");
  const { index, meta } = await assetContext(transport, input.asset);
  const client = new hl.ExchangeClient({
    transport,
    wallet: viemAccount(privy, {
      id: input.agentWalletId,
      address: input.agentWalletAddress,
    }),
  });
  const leverage = Math.max(1, Math.min(Number(input.leverage || 1), Number(meta.maxLeverage || 50)));
  return client.updateLeverage({
    asset: index,
    isCross: input.isCross !== false,
    leverage,
  });
}

async function closePosition(input) {
  const privy = privyClient();
  const transport = transportFor(input.network || "testnet");
  const { index, meta, context } = await assetContext(transport, input.asset);
  const szDecimals = Number(meta.szDecimals || 5);
  const size = formatSize(input.size, szDecimals);
  const isClosingLong = input.side === "long";
  const mark = Number(context?.markPx || input.markPrice || 0);
  if (!mark) throw new Error(`Reference price unavailable for ${input.asset}`);
  const client = new hl.ExchangeClient({
    transport,
    wallet: viemAccount(privy, {
      id: input.agentWalletId,
      address: input.agentWalletAddress,
    }),
  });
  const closePrice = formatPrice(mark * (isClosingLong ? 0.995 : 1.005), szDecimals);
  const close = await client.order({
    grouping: "na",
    orders: [
      {
        a: index,
        b: !isClosingLong,
        s: size,
        p: closePrice,
        r: true,
        t: { limit: { tif: "Ioc" } },
      },
    ],
  });
  return {
    close,
    closeOrderId: extractOrderId(close),
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
  const transfer = await privy.wallets().transfer(input.masterWalletId, {
    destination: {
      address: HYPERLIQUID_BRIDGE2,
      asset: "usdc",
      chain: "arbitrum",
    },
    source: {
      amount: String(amount),
      asset: "usdc",
      chain: "arbitrum",
    },
    amount_type: "exact_input",
    slippage_bps: 0,
  });
  return {
    network: "prodnet",
    protocol: "Privy sponsored Arbitrum USDC -> Hyperliquid Bridge2",
    bridgeAddress: HYPERLIQUID_BRIDGE2,
    usdcAddress: ARBITRUM_USDC,
    amountUsdc: amount,
    actionId: transfer.id,
    hash: transfer.transaction_hash || null,
    status: transfer.status,
    raw: transfer,
  };
}

async function transferUserUsdcToMaster(input) {
  return transferUserUsdc(input, {
    destinationAddress: input.masterWalletAddress,
    destinationLabel: "masterWalletAddress",
    protocol: "Privy sponsored Arbitrum USDC wallet transfer",
    outputAddressKey: "masterWalletAddress",
  });
}

async function transferUserUsdcToExternal(input) {
  return transferUserUsdc(input, {
    destinationAddress: input.externalWalletAddress,
    destinationLabel: "externalWalletAddress",
    protocol: "Privy sponsored Arbitrum USDC external withdrawal",
    outputAddressKey: "externalWalletAddress",
  });
}

async function transferUserUsdc(input, destination) {
  if ((input.network || "testnet") !== "prodnet") {
    throw new Error("Integrated user wallet transfers are only configured for prodnet.");
  }
  const amount = Number(input.amountUsdc || 0);
  if (!Number.isFinite(amount) || amount <= 0) {
    throw new Error("USDC transfer amount must be greater than zero.");
  }
  if (!input.sourceWalletId || !input.sourceWalletAddress || !destination.destinationAddress) {
    throw new Error(
      `sourceWalletId, sourceWalletAddress, and ${destination.destinationLabel} are required`,
    );
  }
  const authorizationJwt = input.userAccessToken || input.userJwt;
  if (!authorizationJwt) {
    throw new Error("Privy user authorization is required for this sponsored transfer.");
  }

  const privy = privyClient();
  const transferParams = {
    authorization_context: { user_jwts: [authorizationJwt] },
    destination: {
      address: destination.destinationAddress,
      asset: "usdc",
      chain: "arbitrum",
    },
    source: {
      amount: String(amount),
      asset: "usdc",
      chain: "arbitrum",
    },
    amount_type: "exact_input",
    slippage_bps: 0,
  };
  const transfer = await privy.wallets().transfer(input.sourceWalletId, transferParams);
  const output = {
    network: "prodnet",
    protocol: destination.protocol,
    sourceWalletId: input.sourceWalletId,
    sourceWalletAddress: input.sourceWalletAddress,
    usdcAddress: ARBITRUM_USDC,
    amountUsdc: amount,
    actionId: transfer.id,
    hash: transfer.transaction_hash || null,
    status: transfer.status,
    raw: transfer,
  };
  output[destination.outputAddressKey] = destination.destinationAddress;
  return output;
}

async function verifyUserJwt(input) {
  if (!input.userJwt) {
    throw new Error("Privy user authorization is required for this sponsored transfer.");
  }
  const privy = privyClient();
  const user = await privy.users().get({ id_token: input.userJwt });
  return {
    valid: true,
    userId: user.id || null,
    appId: null,
    issuedAt: null,
    expiresAt: null,
  };
}

async function verifyUserAccessToken(input) {
  const accessToken = input.userAccessToken || input.userJwt;
  if (!accessToken) {
    throw new Error("Privy user authorization is required for this sponsored transfer.");
  }
  const privy = privyClient();
  const payload = await privy.utils().auth().verifyAccessToken(accessToken);
  return {
    valid: true,
    userId: payload.user_id || null,
    appId: payload.app_id || null,
    issuedAt: payload.issued_at || null,
    expiresAt: payload.expiration || null,
    sessionId: payload.session_id || null,
  };
}

async function verifyUserAuthorizationKey(input) {
  const accessToken = input.userAccessToken || input.userJwt;
  if (!accessToken) {
    throw new Error("Privy user authorization is required for this sponsored transfer.");
  }
  const privy = privyClient();
  await privy._jwtExchange().exchangeJwtForAuthorizationKey(accessToken);
  return {
    valid: true,
    authorizationKeyAvailable: true,
  };
}

try {
  const input = await readStdin();
  let output;
  if (command === "setup-agent") output = await setupAgent(input);
  else if (command === "execute-plan") output = await executePlan(input);
  else if (command === "set-protection") output = await setProtection(input);
  else if (command === "set-leverage") output = await setLeverage(input);
  else if (command === "close-position") output = await closePosition(input);
  else if (command === "wallet-state") output = await walletState(input);
  else if (command === "deposit-master") output = await depositMaster(input);
  else if (command === "transfer-user-usdc-to-master") output = await transferUserUsdcToMaster(input);
  else if (command === "transfer-user-usdc-to-external") output = await transferUserUsdcToExternal(input);
  else if (command === "verify-user-jwt") output = await verifyUserJwt(input);
  else if (command === "verify-user-access-token") output = await verifyUserAccessToken(input);
  else if (command === "verify-user-authorization-key") output = await verifyUserAuthorizationKey(input);
  else throw new Error(`Unknown command: ${command}`);
  process.stdout.write(JSON.stringify(output));
} catch (error) {
  process.stderr.write(formatError(error));
  process.exit(1);
}
