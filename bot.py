from web3 import Web3
import datetime
import json
import secret_keys
import argparse


WEI_PER_ETH = 1000000000000000000


class Arbitrageur:
    """
    Arbitrageur bot that takes in token ABI & a list of dexes as parameter.
    Bot gets token & ETH reserves in each pool by querying its balance in the token & WETH smart contracts.
    Bot calculates the buy & sell prices of a simple, single round-trip arbitrage that is initiated by selling 0.0001ETH.
    Bot detects arb opportunities by checking if it ends up w more ETH at the end.
    Arbitrage detection is optimised by sorting the buy-leg by how much DAI we get (desc) and
    the sell-leg by how much ETH we get (desc). if we detect an arb opportunity, it is automatically the
    most profitable one that we should pursue, so we exit.
    """

    def __init__(self, abi, dexes, eth_trade_amount, profit_threshold) -> None:
        self.w3 = Web3(Web3.HTTPProvider(secret_keys.ALCHEMY))
        self.abi = abi
        self.dexes = dexes
        self.eth_trade_amount = float(eth_trade_amount)
        self.profit_threshold = float(profit_threshold)
        # tracks the ETH & DAI reserves in these pools
        # DAI and ETH reserves are measured in DAI * 10^18 and WEI
        self.reserves = {dex: {"dai": 0, "eth": 0} for dex in dexes}

        # tracks the DAI buy prices & dai amount from selling 0.0001ETH
        # AND ETH sell prices from selling the dat amount
        self.prices = {
            dex: {
                "buy_price": 0,  # price of DAI in ETH
                "dai_amount": 0,  # amt of DAI bought by 0.0001ETH
                "sale": {
                    other_dex: {
                        "sell_price": 0,  # price of ETH in DAI
                        "eth_amount": 0,  # amt of ETH bought by dai_amount
                    }
                    for other_dex in dexes
                    if other_dex != dex
                },
            }
            for dex in dexes
        }

        # tracks arb opportunities
        self.opps = []

    # returns price of ETH in terms of DAI
    def price_eth(self):
        return self.token_reserve / self.eth_reserve

    # returns price of token (DAI) in temrs of ETH
    def price_token(self):
        return self.eth_reserve / self.token_reserve

    def get_balances(self, exchange_addr):
        weth = self.w3.eth.contract(WETH, abi=self.abi)
        dai = self.w3.eth.contract(DAI, abi=self.abi)
        weth_balance = weth.functions.balanceOf(exchange_addr).call()
        dai_balance = dai.functions.balanceOf(exchange_addr).call()
        return weth_balance, dai_balance

    def gather_data(self):
        for dex, address in self.dexes.items():
            weth_balance, dai_balance = self.get_balances(address)
            self.reserves[dex]["eth"] = weth_balance
            self.reserves[dex]["dai"] = dai_balance

    def swap_eth_for_token(self, eth_reserve, token_reserve, eth_in):
        # ETH and DAI reserve measureed in 10^18
        eth_in_wei = int(eth_in * WEI_PER_ETH)

        numerator = token_reserve * eth_in_wei
        denominator = eth_reserve + eth_in_wei

        token_out = numerator / denominator
        eth_price = (token_reserve - token_out) / (eth_reserve + eth_in_wei)

        return token_out / WEI_PER_ETH, eth_price

    def swap_token_for_eth(self, token_reserve, eth_reserve, token_in):
        # ETH and DAI reserve measureed in 10^18
        token_in_unit = int(token_in * WEI_PER_ETH)

        numerator = eth_reserve * token_in_unit
        denominator = token_reserve + token_in_unit

        eth_out = numerator / denominator
        token_price = (eth_reserve - eth_out) / (token_reserve + token_in_unit)

        return eth_out / WEI_PER_ETH, token_price

    def calculate_prices_from_data(self):
        # buy low, sell high
        for buy_exchange, buy_r in self.reserves.items():
            dai_amount, eth_price = self.swap_eth_for_token(
                buy_r["eth"], buy_r["dai"], self.eth_trade_amount
            )
            self.prices[buy_exchange]["buy_price"] = eth_price  # in DAI
            self.prices[buy_exchange]["dai_amount"] = dai_amount  # amt of dai
            print(
                f"# Buying {dai_amount} DAI using {eth_trade_amount} ETH at a price of {eth_price} DAI/ETH at {buy_exchange}"
            )

            for sell_exchange, sell_r in self.reserves.items():
                if sell_exchange != buy_exchange:
                    eth_amount, dai_price = self.swap_token_for_eth(
                        sell_r["dai"],
                        sell_r["eth"],
                        dai_amount,
                    )
                    self.prices[buy_exchange]["sale"][sell_exchange][
                        "sell_price"
                    ] = dai_price
                    self.prices[buy_exchange]["sale"][sell_exchange][
                        "eth_amount"
                    ] = eth_amount

                    print(
                        f"## Buying {eth_amount} ETH using {dai_amount} DAI at price of {dai_price} ETH/DAI at {sell_exchange}"
                    )

    def check_for_arbitrage(self, block_number):
        arb_opps = []
        # sort by how much DAI we can buy to ensure the first arb we find is the most profitable and can exit
        sorted_buys = sorted(
            self.prices.items(), key=lambda x: x[1]["dai_amount"], reverse=True
        )

        # try selling ETH for DAI, then selling DAI for ETH.
        # if more ETH to begin with than the beginning, then profitable arbitrage found.

        for buy_exchange, buy_details in sorted_buys:
            dai_amount = buy_details["dai_amount"]
            eth_price = buy_details["buy_price"]  # in DAI/ETH

            # sort by how much ETH we can buy to ensure the first arb we find is the most profitable and can exit
            sorted_sells = sorted(
                buy_details["sale"].items(),
                key=lambda x: x[1]["eth_amount"],
                reverse=True,
            )
            # print(
            #     f"# Buy {dai_amount} DAI using {self.eth_trade_amount} ETH at a price of {eth_price} DAI/ETH, from {buy_exchange}"
            # )

            for sell_exchange, sell_details in sorted_sells:
                if buy_exchange != sell_exchange:
                    eth_amount = sell_details["eth_amount"]
                    dai_price = sell_details["sell_price"]

                    profit = eth_amount - self.eth_trade_amount
                    if profit > self.profit_threshold:
                        print(
                            "** Profit: {} ETH -> {} DAI -> {} ETH, from {} to {}. {:.20f} ETH in Profit".format(
                                self.eth_trade_amount,
                                dai_amount,
                                eth_amount,
                                buy_exchange,
                                sell_exchange,
                                profit,
                            )
                        )

                        arb_opps.append(
                            {
                                "block_number": block_number,
                                "profit (ETH)": profit,  # how much ETH this arbitrage makes
                                "buy_exchange": buy_exchange,  # exchange to buy DAI using ETH
                                "buy_price": f"{eth_price} DAI/ETH",  # price of ETH that arbitrage paid
                                "buy_quote": (
                                    f"{self.eth_trade_amount} ETH",  # how much ETH was sold, always 0.0001ETH
                                    f"{dai_amount} DAI",  # how much DAI was bought
                                ),
                                "sell_exchange": sell_exchange,  # exchange to buy ETH using the DAI we just bought
                                "sell_price": f"{dai_price} ETH/DAI",  # price of DAI that the arbitrageur paid
                                "sell_quote": (
                                    f"{dai_amount} DAI",  # how much DAI was sold (same as buy_quote[1])
                                    f"{eth_amount} ETH",  # how much ETH we get at the end
                                ),
                            }
                        )
                        # only get the first and most profitable arbitrage from this round-trip pair
                        # after this, we break into the next buy exchange
                        break

        arb_opps = sorted(arb_opps, key=lambda x: x["profit (ETH)"], reverse=True)
        return arb_opps


# Calculate and print the elapsed time
def print_elapsed_time(start_time):
    elapsed = datetime.datetime.now() - start_time
    days, seconds = elapsed.days, elapsed.seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    print(
        f"Elapsed time: {days} days, {hours} hours, {minutes} minutes, {seconds} seconds"
    )


def test_arbitrage_check(bot):
    bot.reserves = {
        "uniswap": {"dai": 100 * WEI_PER_ETH, "eth": 1 * WEI_PER_ETH},
        "sushiswap": {"dai": 50 * WEI_PER_ETH, "eth": 3 * WEI_PER_ETH},
        "shebaswap": {"dai": 100 * WEI_PER_ETH, "eth": 1 * WEI_PER_ETH},
        "croswap": {"dai": 100 * WEI_PER_ETH, "eth": 1 * WEI_PER_ETH},
    }

    bot.calculate_prices_from_data()
    arbs = bot.check_for_arbitrage(0)
    assert len(arbs) == 3
    for a in arbs:
        assert abs(a["profit (ETH)"] - 0.0005) < 0.000001  # nearly equal


if __name__ == "__main__":
    print("Initializing arbitrageur...")
    parser = argparse.ArgumentParser(description="Process some arguments.")
    parser.add_argument(
        "--eth_trade_amount", type=float, default=0.0001, help="ETH trade amount"
    )
    parser.add_argument(
        "--profit_threshold", type=float, default=0.0000001, help="Profit threshold"
    )

    args = parser.parse_args()

    eth_trade_amount = args.eth_trade_amount
    profit_threshold = args.profit_threshold

    with open("erc20_abi.json") as erc20_abi:
        ERC20_ABI = json.load(erc20_abi)

    UNISWAPV2_ADDR = "0xA478c2975Ab1Ea89e8196811F51A7B7Ade33eB11"
    SUSHISWAP_ADDR = "0xC3D03e4F041Fd4cD388c549Ee2A29a9E5075882f"
    SHEBASWAP_ADDR = "0x8faf958E36c6970497386118030e6297fFf8d275"
    CROSWAP_ADDR = "0x60A26d69263eF43e9a68964bA141263F19D71D51"
    WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    DAI = "0x6B175474E89094C44Da98b954EedeAC495271d0F"

    dexes = {
        "uniswap": UNISWAPV2_ADDR,
        "sushiswap": SUSHISWAP_ADDR,
        "shebaswap": SHEBASWAP_ADDR,
        "croswap": CROSWAP_ADDR,
    }

    bot = Arbitrageur(ERC20_ABI, dexes, eth_trade_amount, profit_threshold)
    test_arbitrage_check(bot)

    try:
        start_time = datetime.datetime.now()
        last_block_number = None
        while True:
            current_block_number = bot.w3.eth.block_number
            # to prevent querying redundant data, we ensure that we only query once when the block is updated
            if last_block_number == None or current_block_number > last_block_number:
                print("Gathering new data from block", current_block_number, "...")
                # if current == last: then we have queried already.
                # if current > last: block has elapsed and we query new data
                # if no last block number, we start afresh and query new data
                bot.gather_data()

                bot.calculate_prices_from_data()
                arb_opps = bot.check_for_arbitrage(current_block_number)

                if len(arb_opps) > 0:
                    print(
                        len(arb_opps),
                        "arbitrage opportunities present in",
                        current_block_number,
                    )
                    bot.opps.extend(arb_opps)
                else:
                    print("no arbitrage opportunity found")

                last_block_number = current_block_number

    except KeyboardInterrupt:
        print_elapsed_time(start_time)
        total_profit = sum(a["profit (ETH)"] for a in bot.opps)
        print(
            f"In total, found {len(bot.opps)} arbitrages that make past the profit threshold, with total profit of {total_profit}"
        )
        with open("arbitrages.json", "w+") as fp:
            json.dump(bot.opps, fp)
        print("Program ends. Dumped all profitable arbitrages into arbitrage.json")


# additional things to implement
#   * adding post-cost profit check (will there be positive profit after the execution)?
#   * adding complex
#   * adding concurrency support (rn since we r only dealing w 4 dexes, doenst seem necessary)
#   * improve arbitrage algorithm, rn O(n^2)
