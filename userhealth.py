
import sys
from tokenize import tabsize
import driftpy
import pandas as pd 
import numpy as np 
from driftpy.math.oracle import *

pd.options.plotting.backend = "plotly"

# from driftpy.constants.config import configs
from anchorpy import Provider, Wallet
from solana.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from driftpy.clearing_house import ClearingHouse
from driftpy.clearing_house_user import ClearingHouseUser
from driftpy.accounts import get_perp_market_account, get_spot_market_account, get_user_account, get_state_account
from driftpy.constants.numeric_constants import * 
from driftpy.clearing_house_user import get_token_amount
import os
import json
import streamlit as st
from driftpy.types import MarginRequirementType
from driftpy.constants.banks import devnet_banks, Bank
from driftpy.constants.markets import devnet_markets, Market
from driftpy.addresses import *
from dataclasses import dataclass
from solana.publickey import PublicKey
from helpers import serialize_perp_market_2, serialize_spot_market
from anchorpy import EventParser
import asyncio
import time
from enum import Enum
from driftpy.math.margin import MarginCategory, calculate_asset_weight

async def show_user_health(clearing_house: ClearingHouse):
    state = await get_state_account(clearing_house.program)
    user_authority = st.text_input('user authority', '882DFRCi5akKFyYxT4PP2vZkoQEGvm2Nsind2nPDuGqu')

    if user_authority != '':
        ch = clearing_house
        user_authority_pk = PublicKey(user_authority)

        chu = ClearingHouseUser(
            ch, 
            authority=user_authority_pk, 
            subaccount_id=0, 
            use_cache=False
        )
        # await chu.set_cache()
        # cache = chu.CACHE

        user_stats_pk = get_user_stats_account_public_key(ch.program_id, user_authority_pk)
        all_user_stats = await ch.program.account['UserStats'].fetch(user_stats_pk)

        all_summarys = []
        for x in range(all_user_stats.number_of_sub_accounts_created):
            chu_sub = ClearingHouseUser(
                ch, 
                authority=user_authority_pk, 
                subaccount_id=x, 
                use_cache=True
            )
            CACHE = None   
            try:
                await chu_sub.set_cache_last(CACHE)
            except:
                continue
            summary = {}
            summary['total_collateral'] = (await chu_sub.get_total_collateral())/1e6
            summary['init total_collateral'] = (await chu_sub.get_total_collateral(MarginCategory.INITIAL))/1e6
            summary['maint total_collateral'] = (await chu_sub.get_total_collateral(MarginCategory.MAINTENANCE))/1e6
            summary['initial_margin_req'] = (await chu_sub.get_margin_requirement(MarginCategory.INITIAL, None, True, False))/1e6
            summary['maintenance_margin_req'] = (await chu_sub.get_margin_requirement(MarginCategory.MAINTENANCE, None, True, False))/1e6
            all_summarys.append(pd.DataFrame(summary, index=[x]))

            balances = []
            for x in range(state.number_of_spot_markets):
                spot_pos = await chu_sub.get_user_spot_position(x)
                if spot_pos is not None:
                    spot = await chu_sub.get_spot_market(x)
                    tokens = get_token_amount(
                        spot_pos.scaled_balance,
                        spot, 
                        str(spot_pos.balance_type)
                    )
                    market_name = ''.join(map(chr, spot.name)).strip(" ")

                    dd = {
                     'name': market_name,
                     'tokens': tokens/(10**spot.decimals),
                     'net usd value': await chu_sub.get_spot_market_asset_value(None, False, x)/1e6,
                     'asset weight': calculate_asset_weight(tokens, spot, None)/1e4,
                     'initial asset weight': calculate_asset_weight(tokens, spot, MarginCategory.INITIAL)/1e4,
                     'maint asset weight': spot.maintenance_asset_weight/1e4,
                     'your maint asset weight': calculate_asset_weight(tokens, spot, MarginCategory.MAINTENANCE)/1e4,
                     'weighted usd value': await chu_sub.get_spot_market_asset_value(MarginCategory.INITIAL, False, x)/1e6,
                     'maint weighted usd value': await chu_sub.get_spot_market_asset_value(MarginCategory.MAINTENANCE, False, x)/1e6,
                     'liq price': await chu_sub.get_spot_liq_price(x)
                    }
                    balances.append(dd)



        sub_dfs = pd.concat(all_summarys)
        sub_dfs.index.name = 'subaccount_id'
        st.markdown('summary')
        st.dataframe(sub_dfs)

        st.markdown('assets/liabilities')
        st.dataframe(pd.DataFrame(balances).T)

        st.markdown('user stats')
        st.dataframe(pd.DataFrame(all_user_stats.__dict__).T[0])


    else:
        st.text('not found')

    
    