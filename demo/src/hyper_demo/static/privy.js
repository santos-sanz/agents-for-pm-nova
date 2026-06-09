const PRIVY_SDK_URL = "https://esm.sh/@privy-io/js-sdk-core@latest";
const ARBITRUM_CHAIN_ID = "0xa4b1";
const ARBITRUM_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";
const ARBITRUM_PARAMS = {
  chainId: ARBITRUM_CHAIN_ID,
  chainName: "Arbitrum One",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: ["https://arb1.arbitrum.io/rpc"],
  blockExplorerUrls: ["https://arbiscan.io"],
};

window.hyperDemoPrivyFunding = { ready: false };

let privyClient = null;
let privyUser = null;
let privyHelpers = null;

const $ = (selector) => document.querySelector(selector);

function setStatus(value) {
  for (const el of document.querySelectorAll("#privy-status, #privy-auth-status")) {
    el.textContent = value;
  }
}

function errorMessage(error) {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return "Unexpected Privy error";
  }
}

function walletFromUser(user) {
  if (!user) return null;
  const linked = user.linkedAccounts || user.linked_accounts || [];
  return linked.find((account) => {
    const type = account.type || account.accountType || account.kind;
    return String(type || "").toLowerCase().includes("wallet") && account.address;
  });
}

function parseDecimalUnits(value, decimals) {
  const raw = String(value || "").trim();
  if (!/^\d+(\.\d+)?$/.test(raw)) throw new Error("Enter a valid amount.");
  const [whole, fraction = ""] = raw.split(".");
  if (fraction.length > decimals) throw new Error(`Amount supports up to ${decimals} decimals.`);
  return BigInt(whole) * 10n ** BigInt(decimals) + BigInt(fraction.padEnd(decimals, "0") || "0");
}

function encodeErc20Transfer(to, amount) {
  const cleanTo = String(to || "").replace(/^0x/, "").toLowerCase();
  if (!/^[0-9a-f]{40}$/.test(cleanTo)) throw new Error("Destination wallet is invalid.");
  const addressArg = cleanTo.padStart(64, "0");
  const amountArg = amount.toString(16).padStart(64, "0");
  return `0xa9059cbb${addressArg}${amountArg}`;
}

async function getEmbeddedProvider() {
  const privy = await ensurePrivy();
  if (!privyUser) {
    const session = await privy.user.get();
    privyUser = session?.user || null;
  }
  if (!privyUser) throw new Error("Connect the Privy wallet first.");
  const wallet = privyHelpers.getUserEmbeddedEthereumWallet(privyUser);
  if (!wallet?.address) throw new Error("Privy embedded wallet is not available.");
  const { entropyId, entropyIdVerifier } = privyHelpers.getEntropyDetailsFromUser(privyUser);
  const provider = await privy.embeddedWallet.getEthereumProvider({
    wallet,
    entropyId,
    entropyIdVerifier,
  });
  return { provider, wallet };
}

async function ensureArbitrum(provider) {
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: ARBITRUM_CHAIN_ID }],
    });
  } catch (error) {
    await provider.request({
      method: "wallet_addEthereumChain",
      params: [ARBITRUM_PARAMS],
    });
  }
}

async function transferUserUsdcToMaster({ masterAddress, amountUsdc }) {
  const { provider, wallet } = await getEmbeddedProvider();
  await ensureArbitrum(provider);
  const amount = parseDecimalUnits(amountUsdc, 6);
  if (amount <= 0n) throw new Error("USDC amount must be greater than 0.");
  return provider.request({
    method: "eth_sendTransaction",
    params: [
      {
        from: wallet.address,
        to: ARBITRUM_USDC,
        value: "0x0",
        data: encodeErc20Transfer(masterAddress, amount),
      },
    ],
  });
}

async function saveWallet(address, user, email) {
  const saved = await window.hyperDemo.api("/api/wallet/connected", {
    method: "POST",
    body: JSON.stringify({
      address,
      user_id: user?.id || user?.userId || null,
      email: email || user?.email?.address || user?.email || null,
      wallet_id: walletFromUser(user)?.id || walletFromUser(user)?.walletId || null,
    }),
  });
  window.hyperDemo.state.connected_wallet = saved;
  await window.hyperDemo.loadState();
  return saved;
}

async function ensurePrivy() {
  if (privyClient) return privyClient;
  const config = await window.hyperDemo.api("/api/privy/config");
  if (!config.configured) {
    setStatus("missing config");
    throw new Error("Set PRIVY_APP_ID and PRIVY_CLIENT_ID in demo/.env.");
  }

  privyHelpers = await import(PRIVY_SDK_URL);
  const Privy = privyHelpers.default;
  privyClient = new Privy({
    appId: config.app_id,
    clientId: config.client_id,
    storage: new privyHelpers.LocalStorage(),
  });

  const iframe = document.createElement("iframe");
  iframe.src = privyClient.embeddedWallet.getURL();
  const iframeOrigin = new URL(iframe.src).origin;
  iframe.title = "Privy secure wallet context";
  iframe.hidden = true;
  document.body.appendChild(iframe);
  iframe.addEventListener(
    "load",
    () => {
      privyClient.setMessagePoster(iframe.contentWindow);
      window.addEventListener("message", (event) => {
        if (event.source !== iframe.contentWindow || event.origin !== iframeOrigin) return;
        privyClient.embeddedWallet.onMessage(event.data);
      });
    },
    { once: true },
  );
  setStatus("ready");
  return privyClient;
}

async function sendCode() {
  const email = $("#privy-email").value.trim();
  if (!email) throw new Error("Enter an email for Privy login.");
  const privy = await ensurePrivy();
  await privy.auth.email.sendCode(email);
  setStatus("code sent");
  window.hyperDemo.toast("Privy code sent");
}

async function connect() {
  const email = $("#privy-email").value.trim();
  const code = $("#privy-code").value.trim();
  if (!email || !code) throw new Error("Enter email and code.");
  const privy = await ensurePrivy();
  const session = await privy.auth.email.loginWithCode(email, code);
  privyUser = session.user;
  const wallet = walletFromUser(privyUser);
  if (wallet?.address) {
    await saveWallet(wallet.address, privyUser, email);
    setStatus("connected");
    window.hyperDemo.toast("Privy wallet connected");
    return;
  }
  setStatus("authenticated");
  window.hyperDemo.toast("Privy login complete");
}

async function createOrLinkWallet() {
  const privy = await ensurePrivy();
  if (!privyUser) {
    await connect();
  }
  const existing = walletFromUser(privyUser);
  if (existing?.address) {
    await saveWallet(existing.address, privyUser, $("#privy-email").value.trim());
    setStatus("connected");
    return;
  }
  const result = await privy.embeddedWallet.create({});
  privyUser = result.user;
  const wallet = privyHelpers.getUserEmbeddedEthereumWallet(privyUser);
  if (!wallet?.address) throw new Error("Privy did not return an embedded EVM wallet.");
  await saveWallet(wallet.address, privyUser, $("#privy-email").value.trim());
  setStatus("wallet linked");
  window.hyperDemo.toast("Privy wallet linked");
}

document.addEventListener("click", async (event) => {
  const action = event.target.dataset.action;
  if (!action?.startsWith("privy-")) return;
  try {
    if (action === "privy-send-code") await sendCode();
    if (action === "privy-connect") await connect();
    if (action === "privy-create-wallet") await createOrLinkWallet();
  } catch (error) {
    setStatus("error");
    window.hyperDemo.toast(errorMessage(error));
  }
});

$("#privy-auth-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await createOrLinkWallet();
  } catch (error) {
    setStatus("error");
    window.hyperDemo.toast(errorMessage(error));
  }
});

ensurePrivy().catch(() => {});

window.hyperDemoPrivyFunding = {
  ready: true,
  transferUserUsdcToMaster,
};
