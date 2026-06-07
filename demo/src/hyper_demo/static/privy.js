const PRIVY_SDK_URL = "https://esm.sh/@privy-io/js-sdk-core@latest";

let privyClient = null;
let privyUser = null;
let privyHelpers = null;

const $ = (selector) => document.querySelector(selector);

function setStatus(value) {
  const el = $("#privy-status");
  if (el) el.textContent = value;
}

function walletFromUser(user) {
  if (!user) return null;
  const linked = user.linkedAccounts || user.linked_accounts || [];
  return linked.find((account) => {
    const type = account.type || account.accountType || account.kind;
    return String(type || "").toLowerCase().includes("wallet") && account.address;
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
  iframe.title = "Privy secure wallet context";
  iframe.hidden = true;
  document.body.appendChild(iframe);
  iframe.addEventListener(
    "load",
    () => {
      privyClient.setMessagePoster(iframe.contentWindow);
      window.addEventListener("message", (event) => {
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
    window.hyperDemo.toast(error.message);
  }
});

ensurePrivy().catch(() => {});
