import logging
import numpy as np
from config import WALL_RANGE_SPREAD, MIN_WALL_VOLUME, PRICE_PRECISION

logger = logging.getLogger(__name__)
def filter_walls(orderbook, current_price, threshold=0.002):
    logger.info(f"Ulaz u filter_walls: current_price={current_price}, threshold={threshold}")
    if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
        logger.error(f"Orderbook nije ispravan: {orderbook}")
        return {'support': [], 'resistance': []}

    bids = np.array(orderbook['bids'], dtype=float)
    asks = np.array(orderbook['asks'], dtype=float)
    bid_volumes = bids[:, 1]
    ask_volumes = asks[:, 1]
    total_bid_volume = sum(bid_volumes)
    total_ask_volume = sum(ask_volumes)
    logger.info(f"Bids: {len(bids)}, Asks: {len(asks)}, Total bid volume: {total_bid_volume:.2f}, Total ask volume: {total_ask_volume:.2f}")

    support_walls = []
    for i in range(len(bids) - 3):  # Smanjeno na 3
        cluster_volumes = bid_volumes[i:i + 3]
        cluster_prices = bids[i:i + 3, 0]
        cluster_volume = sum(cluster_volumes)
        price_spread = max(cluster_prices) - min(cluster_prices)
        logger.debug(f"Support cluster {i}: volume={cluster_volume:.2f}, price_spread={price_spread:.5f}")
        if price_spread <= WALL_RANGE_SPREAD and cluster_volume >= MIN_WALL_VOLUME:
            avg_price = np.mean(cluster_prices)
            avg_price = round(float(avg_price), PRICE_PRECISION)
            support_walls.append([avg_price, cluster_volume])
            logger.info(f"Support wall: price={avg_price:.5f}, volume={cluster_volume:.2f}")

    resistance_walls = []
    for i in range(len(asks) - 3):  # Smanjeno na 3
        cluster_volumes = ask_volumes[i:i + 3]
        cluster_prices = asks[i:i + 3, 0]
        cluster_volume = sum(cluster_volumes)
        price_spread = max(cluster_prices) - min(cluster_prices)
        logger.debug(f"Resistance cluster {i}: volume={cluster_volume:.2f}, price_spread={price_spread:.5f}")
        if price_spread <= WALL_RANGE_SPREAD and cluster_volume >= MIN_WALL_VOLUME:
            avg_price = np.mean(cluster_prices)
            avg_price = round(float(avg_price), PRICE_PRECISION)
            resistance_walls.append([avg_price, cluster_volume])
            logger.info(f"Resistance wall: price={avg_price:.5f}, volume={cluster_volume:.2f}")

    walls = {'support': support_walls, 'resistance': resistance_walls}
    logger.info(f"Pronađeni zidovi: support={len(support_walls)}, resistance={len(resistance_walls)}")
    return walls


def detect_trend(orderbook, current_price):
    logger.info(f"Ulaz u detect_trend: current_price={current_price}")
    buy_pressure = sum([float(amount) for price, amount in orderbook['bids'] if float(price) > current_price * 0.99])
    sell_pressure = sum([float(amount) for price, amount in orderbook['asks'] if float(price) < current_price * 1.01])
    logger.info(f"Buy pressure: {buy_pressure:.2f}, Sell pressure: {sell_pressure:.2f}")
    if buy_pressure > sell_pressure * 1.2:
        return 'UP'
    elif sell_pressure > buy_pressure * 1.2:
        return 'DOWN'
    return 'NEUTRAL'