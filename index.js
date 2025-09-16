// index.js — bot simples só para !history (o Python é quem publica via WEBHOOK_URL)
require('dotenv').config();
const { Client, GatewayIntentBits } = require('discord.js');
const fs = require('fs');

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent]
});

const HISTORY_FILE = 'matches.json';

function loadHistory() {
  try { return JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf8')); }
  catch { return []; }
}

client.on('messageCreate', (message) => {
  if (message.author.bot) return;
  const m = message.content.trim();

  if (m === '!ping') return message.reply('pong 🏓');

  if (m === '!history') {
    const history = loadHistory();
    if (!history.length) return message.reply('📭 Ainda não há partidas registadas.');
    const last = history.slice(-5);
    const lines = last.map((x, i) => {
      const head = `${i+1}. Match ${x.id||'??'} → ${x.result||'??'} (${x.time||'??'})`;
      const det  = `   🃏 ${x.player_deck||'??'} vs ${x.opponent||'??'}`;
      return `${head}\n${det}`;
    });
    return message.reply('📜 **Últimos jogos MTGA**:\n' + lines.join('\n'));
  }
});

client.once('clientReady', () => {
  console.log(`✅ Bot online como ${client.user.tag}`);
});

client.login(process.env.BOT_TOKEN);
