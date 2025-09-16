# Historian — MTGA Log Watcher

Historian is a tool that **watches your MTG Arena `Player.log`** in real-time and reports what happens in your matches to **Discord**.  
It is useful for tracking decks, plays, and results automatically.

---

## ✨ Features

- 📜 Full **decklist** (main + sideboard) when you queue
- ✋ Shows your **opening hand**
- 📥 Reports **draws** (library → hand)
- 🃏 Logs **plays**: spells cast, permanents entering the battlefield
- 🎮 Detects **match end** (win/loss, even on surrender)
- 💾 Saves local history in `matches.json`
- 🤖 Discord bot with `!history` and `!ping` commands

---

## 📂 Project Structure

 🟢 Deck: Mono-Green (Standard)
**Main**:
4 Llanowar Elves
4 Mossborn Hydra
…

🎮 You entered **Playing** — I’ll start reporting plays.

✋ Your opening hand:
- Fabled Passage
- Mossborn Hydra
- Titanic Growth
…

🃏 You played: **Forest** → battlefield
✨ Opponent cast: **Scorching Dragonfire**
📥 You drew: **Forest**

📜 Match finished!
➡️ Result: **Win**
🃏 You: Mono-Green
⚔️ Opponent: SomeUser
