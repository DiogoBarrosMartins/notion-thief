# Notion Thief — MTGA Log Watcher

Notion Thief is a tool that **watches your MTG Arena `Player.log`** in real-time and reports what happens in your matches to **Discord**.  
It is useful for tracking decks, plays, and results automatically.

---
<img width="389" height="286" alt="Screenshot 2025-09-16 at 11 18 25" src="https://github.com/user-attachments/assets/4d4fc92f-4b8c-4f7a-b255-c78b2b8b849f" />

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
