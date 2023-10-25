# Readme

To activate virtual environment:

```bash
cd ~/path/to/simple-arbitrage-bot
source venv/bin/activate
```

To run arbitrage

```bash
// to run bot with default ETH trading amt (0.0001) and profit threshold (0.0000005)
python3 bot.py

// to run it with custom initial ETH trading amount or custom profit threshold
python3 bot.py --eth_trade_amount=0.0005 --profit_threshold=0.1234
```

To stop the bot, do ctrl-c. All the profitable arbitrages can be found in `arbitrages.json`

