const PRIVY_SDK_URL = "https://esm.sh/@privy-io/js-sdk-core@latest";
const ARBITRUM_CHAIN_ID = "0xa4b1";
const ARBITRUM_USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";

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

function assertEvmAddress(value, label) {
  if (!/^0x[a-fA-F0-9]{40}$/.test(String(value || ""))) {
    throw new Error(`${label} must be a valid EVM address.`);
  }
}

function parseUsdcUnits(value) {
  const raw = String(value || "").trim();
  if (!/^\d+(\.\d{1,6})?$/.test(raw)) throw new Error("USDC amount must use up to 6 decimals.");
  const [whole, fraction = ""] = raw.split(".");
  const units = BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(6, "0"));
  if (units <= 0n) throw new Error("USDC amount must be greater than zero.");
  return units;
}

function pad64(value) {
  return String(value).replace(/^0x/, "").padStart(64, "0");
}

function encodeUsdcTransfer(to, amount) {
  return `0xa9059cbb${pad64(to.toLowerCase())}${pad64(amount.toString(16))}`;
}

function normalizeTransferError(error) {
  const message = errorMessage(error);
  if (message.toLowerCase().includes("insufficient funds")) {
    return new Error("Source wallet has 0 ETH on Arbitrum. Add a small amount of ETH for gas before sending USDC.");
  }
  return error;
}

async function currentUser() {
  const privy = await ensurePrivy();
  if (privyUser) return privyUser;
  const response = await privy.user.get();
  privyUser = response?.user || response || null;
  if (!privyUser) throw new Error("Log in with Privy before sending USDC.");
  return privyUser;
}

async function embeddedProviderForUser() {
  const privy = await ensurePrivy();
  const user = await currentUser();
  const wallet = privyHelpers.getUserEmbeddedEthereumWallet(user);
  if (!wallet?.address) throw new Error("Privy embedded EVM wallet is not linked.");
  const entropy = privyHelpers.getEntropyDetailsFromUser(user);
  const provider = await privy.embeddedWallet.getEthereumProvider({
    wallet,
    entropyId: entropy.entropyId,
    entropyIdVerifier: entropy.entropyIdVerifier,
  });
  return { provider, wallet };
}

async function ensureArbitrum(provider) {
  const chainId = await provider.request({ method: "eth_chainId", params: [] });
  if (String(chainId).toLowerCase() === ARBITRUM_CHAIN_ID) return;
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: ARBITRUM_CHAIN_ID }],
    });
  } catch (error) {
    await provider.request({
      method: "wallet_addEthereumChain",
      params: [
        {
          chainId: ARBITRUM_CHAIN_ID,
          chainName: "Arbitrum One",
          nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
          rpcUrls: ["https://arb1.arbitrum.io/rpc"],
          blockExplorerUrls: ["https://arbiscan.io"],
        },
      ],
    });
  }
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
  await privyClient.initialize();

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
  const response = await privyClient.user.get();
  privyUser = response?.user || response || null;
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

async function transferNativeUsdc({ from, to, amount, token = ARBITRUM_USDC_ADDRESS }) {
  assertEvmAddress(from, "Source wallet");
  assertEvmAddress(to, "Destination wallet");
  assertEvmAddress(token, "USDC contract");
  const amountUnits = parseUsdcUnits(amount);
  const { provider, wallet } = await embeddedProviderForUser();
  if (wallet.address.toLowerCase() !== from.toLowerCase()) {
    throw new Error("Privy session wallet does not match the selected source wallet.");
  }
  await ensureArbitrum(provider);
  let hash;
  try {
    hash = await provider.request({
      method: "eth_sendTransaction",
      params: [
        {
          from,
          to: token,
          value: "0x0",
          data: encodeUsdcTransfer(to, amountUnits),
        },
      ],
    });
  } catch (error) {
    throw normalizeTransferError(error);
  }
  return { hash, from, to, amount: String(amount), token, chainId: ARBITRUM_CHAIN_ID };
}

async function getAccessToken() {
  const privy = await ensurePrivy();
  const response = await privy.user.get();
  privyUser = response?.user || response || null;
  if (!privyUser) {
    const savedEmail = $("#privy-email")?.value.trim() || "";
    await privy.auth.logout({ userId: "*" }).catch(() => {});
    if (savedEmail) $("#privy-email").value = savedEmail;
    throw new Error("Log in with Privy before submitting a sponsored transfer.");
  }
  const token = await privy.getAccessToken();
  if (!token) throw new Error("Log in with Privy before submitting a sponsored transfer.");
  return token;
}

async function getIdentityToken() {
  const privy = await ensurePrivy();
  const response = await privy.user.get();
  privyUser = response?.user || response || null;
  if (!privyUser) {
    const savedEmail = $("#privy-email")?.value.trim() || "";
    await privy.auth.logout({ userId: "*" }).catch(() => {});
    if (savedEmail) $("#privy-email").value = savedEmail;
    throw new Error("Log in with Privy before submitting a sponsored transfer.");
  }
  const token = await privy.getIdentityToken();
  if (!token) throw new Error("Enable Privy identity tokens and log in again before retrying.");
  return token;
}

window.hyperDemoPrivy = {
  getAccessToken,
  getIdentityToken,
  transferNativeUsdc,
};

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
