import base64

import pytest
from algokit_utils import (
    Account,
    EnsureBalanceParameters,
    LogicError,
    TransactionParameters,
    ensure_funded,
    get_account,
)
from algokit_utils.beta.account_manager import AddressAndSigner
from algokit_utils.beta.algorand_client import AlgorandClient
from algokit_utils.beta.composer import (
    AssetCreateParams,
    AssetOptInParams,
    AssetTransferParams,
    PayParams,
)
from algokit_utils.config import config
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.encoding import decode_address, encode_as_bytes
from algosdk.util import algos_to_microalgos
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from smart_contracts.artifacts.auction.auction_client import AuctionClient


@pytest.fixture(scope="session")
def auctioneer(algod_client: AlgodClient) -> Account:
    return get_account(algod_client, "AUCTIONEER", 100)


@pytest.fixture(scope="session")
def auction_asset(algorand_client: AlgorandClient, auctioneer: Account) -> int:
    return algorand_client.send.asset_create(
        AssetCreateParams(
            sender=auctioneer.address, total=100, signer=auctioneer.signer
        )
    )["confirmation"]["asset-index"]


@pytest.fixture(scope="session")
def first_bidder(
    algorand_client: AlgorandClient, auction_asset: int
) -> AddressAndSigner:
    acct = algorand_client.account.random()

    ensure_funded(
        algorand_client.client.algod,
        EnsureBalanceParameters(
            account_to_fund=acct.address,
            min_spending_balance_micro_algos=algos_to_microalgos(100),
        ),
    )
    algorand_client.send.asset_opt_in(
        AssetOptInParams(
            sender=acct.address, asset_id=auction_asset, signer=acct.signer
        )
    )

    return acct


@pytest.fixture(scope="session")
def second_bidder(
    algorand_client: AlgorandClient, auction_asset: int
) -> AddressAndSigner:
    acct = algorand_client.account.random()

    ensure_funded(
        algorand_client.client.algod,
        EnsureBalanceParameters(
            account_to_fund=acct.address,
            min_spending_balance_micro_algos=algos_to_microalgos(100),
        ),
    )
    algorand_client.send.asset_opt_in(
        AssetOptInParams(
            sender=acct.address, asset_id=auction_asset, signer=acct.signer
        )
    )

    return acct


@pytest.fixture(scope="session")
def auction_client(
    algorand_client: AlgorandClient,
    indexer_client: IndexerClient,
    auctioneer: Account,
    auction_asset: int,
) -> AuctionClient:
    config.configure(
        debug=True,
        # trace_all=True,
    )

    client = AuctionClient(
        algorand_client.client.algod,
        creator=auctioneer,
        indexer_client=indexer_client,
    )

    client.create_create(auction_asset=auction_asset, max_quantity=90)
    ensure_funded(
        algorand_client.client.algod,
        EnsureBalanceParameters(
            account_to_fund=client.app_address,
            min_spending_balance_micro_algos=algos_to_microalgos(10),
        ),
    )
    return client


def test_pass_deposit(
    auction_client: AuctionClient,
    algorand_client: AlgorandClient,
    first_bidder: AddressAndSigner,
    second_bidder: AddressAndSigner,
) -> None:
    auction_client.deposit(
        payment=TransactionWithSigner(
            algorand_client.transactions.payment(
                PayParams(
                    sender=first_bidder.address,
                    receiver=auction_client.app_address,
                    amount=algos_to_microalgos(90),
                )
            ),
            signer=first_bidder.signer,
        ),
        transaction_parameters=TransactionParameters(
            signer=first_bidder.signer,
            sender=first_bidder.address,
            boxes=[(0, b"bidders" + decode_address(first_bidder.address))],
        ),
    )
    auction_client.deposit(
        payment=TransactionWithSigner(
            algorand_client.transactions.payment(
                PayParams(
                    sender=second_bidder.address,
                    receiver=auction_client.app_address,
                    amount=algos_to_microalgos(40),
                )
            ),
            signer=second_bidder.signer,
        ),
        transaction_parameters=TransactionParameters(
            signer=second_bidder.signer,
            sender=second_bidder.address,
            boxes=[(0, b"bidders" + decode_address(second_bidder.address))],
        ),
    )

    assert algorand_client.account.get_information(auction_client.app_address)[
        "amount"
    ] == (
        100_000
        + algos_to_microalgos(10)
        + algos_to_microalgos(90)
        + algos_to_microalgos(40)
    )


def test_fail_deposit(
    auction_client: AuctionClient,
    algorand_client: AlgorandClient,
    first_bidder: AddressAndSigner,
) -> None:
    with pytest.raises(LogicError, match="The payment is fraudulent"):
        auction_client.deposit(
            payment=TransactionWithSigner(
                algorand_client.transactions.payment(
                    PayParams(
                        sender=first_bidder.address,
                        receiver=first_bidder.address,
                        amount=algos_to_microalgos(5),
                    )
                ),
                signer=first_bidder.signer,
            ),
            transaction_parameters=TransactionParameters(
                signer=first_bidder.signer,
                sender=first_bidder.address,
                boxes=[(0, b"bidders" + decode_address(first_bidder.address))],
            ),
        )


def test_pass_bid(
    auction_client: AuctionClient,
    algorand_client: AlgorandClient,
    first_bidder: AddressAndSigner,
    second_bidder: AddressAndSigner,
) -> None:
    first_bidder_key = b"bidders" + decode_address(first_bidder.address)
    second_bidder_key = b"bidders" + decode_address(second_bidder.address)
    auction_client.bid(
        price=algos_to_microalgos(3),
        quantity=10,
        transaction_parameters=TransactionParameters(
            signer=first_bidder.signer,
            sender=first_bidder.address,
            boxes=[(0, first_bidder_key)],
        ),
    )
    auction_client.bid(
        price=algos_to_microalgos(2),
        quantity=20,
        transaction_parameters=TransactionParameters(
            signer=second_bidder.signer,
            sender=second_bidder.address,
            boxes=[(0, second_bidder_key)],
        ),
    )

    assert base64.b64decode(
        algorand_client.client.algod.application_box_by_name(
            auction_client.app_id, first_bidder_key
        )["value"]
    ) == encode_as_bytes(algos_to_microalgos(90)) + encode_as_bytes(
        algos_to_microalgos(3)
    ) + encode_as_bytes(
        10
    )
    assert base64.b64decode(
        algorand_client.client.algod.application_box_by_name(
            auction_client.app_id, second_bidder_key
        )["value"]
    ) == encode_as_bytes(algos_to_microalgos(40)) + encode_as_bytes(
        algos_to_microalgos(2)
    ) + encode_as_bytes(
        20
    )


def test_pass_accept(
    auction_client: AuctionClient,
    algorand_client: AlgorandClient,
    auctioneer: Account,
    auction_asset: int,
    first_bidder: AddressAndSigner,
) -> None:
    pre_accept_auctioneer_balance = algorand_client.account.get_information(
        auctioneer.address
    )["amount"]
    pre_accept_bidder_balance = algorand_client.account.get_information(
        first_bidder.address
    )["amount"]
    pre_accept_bidder_asset_balance = algorand_client.account.get_asset_information(
        first_bidder.address, auction_asset
    )["asset-holding"]["amount"]

    auction_client.accept(
        settlement=TransactionWithSigner(
            algorand_client.transactions.asset_transfer(
                AssetTransferParams(
                    sender=auctioneer.address,
                    asset_id=auction_asset,
                    amount=10,
                    receiver=first_bidder.address,
                    signer=auctioneer.signer,
                    extra_fee=2_000,
                )
            ),
            auctioneer.signer,
        ),
        bidder=first_bidder.address,
        price=algos_to_microalgos(3),
        quantity=10,
        transaction_parameters=TransactionParameters(
            boxes=[(0, b"bidders" + decode_address(first_bidder.address))],
        ),
    )

    assert (
        algorand_client.account.get_information(auctioneer.address)["amount"]
        == pre_accept_auctioneer_balance + algos_to_microalgos(30) - 4_000
    )
    assert algorand_client.account.get_information(first_bidder.address)[
        "amount"
    ] == pre_accept_bidder_balance + algos_to_microalgos(60)
    assert (
        algorand_client.account.get_asset_information(
            first_bidder.address, auction_asset
        )["asset-holding"]["amount"]
        == pre_accept_bidder_asset_balance + 10
    )


def test_pass_retract(
    auction_client: AuctionClient,
    algorand_client: AlgorandClient,
    second_bidder: AddressAndSigner,
) -> None:
    pre_retract_bidder_balance = algorand_client.account.get_information(
        second_bidder.address
    )["amount"]

    sp = algorand_client.client.algod.suggested_params()
    sp.flat_fee = True
    sp.fee = 2_000
    auction_client.retract(
        transaction_parameters=TransactionParameters(
            signer=second_bidder.signer,
            sender=second_bidder.address,
            suggested_params=sp,
            boxes=[(0, b"bidders" + decode_address(second_bidder.address))],
        )
    )

    assert (
        algorand_client.account.get_information(second_bidder.address)["amount"]
        == pre_retract_bidder_balance + algos_to_microalgos(40) - 2_000
    )
