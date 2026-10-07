import type { CapacitorConfig } from "@capacitor/cli";

// A app carrega o site Django (server-rendered); o casco nativo acrescenta push, leitor de QR e ícone nas lojas.
// URL de produção por omissão; para testar contra o PC: RWB_APP_URL=http://10.0.2.2:8000 npx cap sync android
const url = process.env.RWB_APP_URL || "https://app.runwithbroto.co.mz";
const host = new URL(url).host;

const config: CapacitorConfig = {
  appId: "co.mz.runwithbroto.app",
  appName: "RunWithBroto",
  webDir: "www",
  server: {
    url,
    cleartext: url.startsWith("http://"), // só para desenvolvimento no emulador
    allowNavigation: [host],
  },
  // O Django usa este sufixo para saber que o pedido vem da app (ex.: esconder o botão "Instalar app")
  appendUserAgent: "RWBApp/1.0",
  android: { allowMixedContent: false },
  plugins: {
    SplashScreen: { launchShowDuration: 800, backgroundColor: "#0B0B0B", showSpinner: false },
    StatusBar: { style: "DARK", backgroundColor: "#0B0B0B" },
    PushNotifications: { presentationOptions: ["badge", "sound", "alert"] },
  },
};

export default config;
