import logging

import algokit_utils
from algokit_utils.beta.algorand_client import AlgorandClient
from algokit_utils.beta.client_manager import AlgoSdkClients
from algokit_utils.beta.composer import AssetCreateParams
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from smart_contracts.artifacts.auction.auction_client import CreateArgs, DeployCreate

logger = logging.getLogger(__name__)


# define deployment behaviour based on supplied app spec
def deploy(
    algod_client: AlgodClient,
    indexer_client: IndexerClient,
    app_spec: algokit_utils.ApplicationSpecification,
    deployer: algokit_utils.Account,
) -> None:
    from smart_contracts.artifacts.auction.auction_client import (
        AuctionClient,
    )

    algorand_client = AlgorandClient.from_clients(
        AlgoSdkClients(algod_client, indexer_client)
    )
    app_client = AuctionClient(
        algod_client,
        creator=deployer,
        indexer_client=indexer_client,
    )

    auction_asset = algorand_client.send.asset_create(
        AssetCreateParams(
            sender=deployer.address,
            total=100,
            signer=deployer.signer,
        )
    )["confirmation"]["asset-index"]

    app_client.deploy(
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
        on_update=algokit_utils.OnUpdate.AppendApp,
        create_args=DeployCreate(
            args=CreateArgs(auction_asset=auction_asset, max_quantity=90)
        ),
    )
