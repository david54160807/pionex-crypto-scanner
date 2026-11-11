const TEST_SIGNAL = [
  "🤖派網加密貨幣掃描器",
  "━━━━━━━━━━━━━━━━━━",
  "⭐️ <b>BTC / USDT</b>",
  "",
  "🟢 策略判斷：全部條件符合",
  "",
  "📈 波段高點",
  "🔺 H1｜98,500｜量 1,245.68｜RSI 72.40",
  "🔺 H2｜100,200｜量 1,018.35｜RSI 68.20",
  "🔺 H3｜102,800｜量 862.91｜RSI 63.10",
  "",
  "📉 波段低點",
  "🔻 L1｜91,200",
  "🔻 L2｜93,100",
  "🔻 L3｜95,400",
  "━━━━━━━━━━━━━━━━━━",
  "⚙️ 版本 2.0",
  "⚠️ 此為虛擬測試訊號，非即時行情或真實交易訊號。"
].join("\n");

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Pionex Telegram Webhook OK", {
        status: 200
      });
    }

    const suppliedSecret = request.headers.get(
      "X-Telegram-Bot-Api-Secret-Token"
    );

    if (
      !env.TELEGRAM_WEBHOOK_SECRET ||
      suppliedSecret !== env.TELEGRAM_WEBHOOK_SECRET
    ) {
      return new Response("Unauthorized", { status: 401 });
    }

    let update;

    try {
      update = await request.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    const message = update.message;
    if (!message || !message.chat || !message.text) {
      return new Response("OK", { status: 200 });
    }

    const chatId = String(message.chat.id);
    const allowedChatId = String(env.TELEGRAM_CHAT_ID || "");
    const text = message.text.trim().toUpperCase();

    if (!allowedChatId || chatId !== allowedChatId) {
      return new Response("OK", { status: 200 });
    }

    if (text !== "TEST") {
      return new Response("OK", { status: 200 });
    }

    if (!env.TELEGRAM_BOT_TOKEN) {
      return new Response("Missing bot token", { status: 500 });
    }

    const telegramResponse = await fetch(
      `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          chat_id: chatId,
          text: TEST_SIGNAL,
          parse_mode: "HTML",
          disable_web_page_preview: true
        })
      }
    );

    if (!telegramResponse.ok) {
      return new Response("Telegram send failed", { status: 502 });
    }

    return new Response("TEST signal sent", { status: 200 });
  }
};
