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

To stop the bot, do ctrl-c. All the profitable arbitrages can be found in `arbitrages.json`. Example arbitrage object

```json
  {
    "block_number": 18424746,
    "profit (ETH)": 3.4717651866643915e-7,
    "buy_exchange": "croswap",
    "buy_price": "1794.4000111727923 DAI/ETH",
    "buy_quote": ["0.0001 ETH", "0.1794404612016423 DAI"],
    "sell_exchange": "shebaswap",
    "sell_price": "0.000559220301180098 ETH/DAI",
    "sell_quote": ["0.1794404612016423 DAI", "0.00010034717651866644 ETH"]
  },
```
