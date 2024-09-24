from algopy import (
    Account,
    ARC4Contract,
    Asset,
    BoxMap,
    Global,
    Txn,
    UInt64,
    arc4,
    gtxn,
    itxn,
)


class Bidder(arc4.Struct, kw_only=True):
    deposited: arc4.UInt64
    price: arc4.UInt64
    quantity: arc4.UInt64


class Auction(ARC4Contract):
    def __init__(self) -> None:
        self.asset: Asset
        self.max_quantity: UInt64

        self.bidders = BoxMap(Account, Bidder)

    @arc4.abimethod(create="require")
    def create(self, auction_asset: Asset, max_quantity: UInt64) -> None:
        self.asset = auction_asset
        self.max_quantity = max_quantity

    @arc4.abimethod
    def deposit(self, payment: gtxn.PaymentTransaction) -> None:
        # FIXME: Stop deposit once the auction is over.
        assert payment.receiver == Global.current_application_address
        assert payment.amount > 0

        if Txn.sender not in self.bidders:
            self.bidders[Txn.sender] = Bidder(
                deposited=arc4.UInt64(payment.amount),
                price=arc4.UInt64(0),
                quantity=arc4.UInt64(0),
            )
        else:
            self.bidders[Txn.sender].deposited = arc4.UInt64(
                self.bidders[Txn.sender].deposited.native + payment.amount
            )

    @arc4.abimethod
    def bid(self, price: arc4.UInt64, quantity: arc4.UInt64) -> None:
        # FIXME: Stop bids once the auction is over.
        current_deposited = self.bidders[Txn.sender].deposited.native

        assert quantity.native <= self.max_quantity
        assert quantity.native * price.native <= current_deposited

        self.bidders[Txn.sender].price = price
        self.bidders[Txn.sender].quantity = quantity

    @arc4.abimethod
    def accept(
        self,
        settlement: gtxn.AssetTransferTransaction,
        bidder: Account,
        price: arc4.UInt64,
        quantity: arc4.UInt64,
    ) -> None:
        # FIXME: We need to stop the auction once it's been accepted.
        assert Txn.sender == Global.creator_address

        accepted_bidder = self.bidders[bidder].copy()
        del self.bidders[bidder]

        assert settlement.xfer_asset == self.asset
        assert settlement.asset_receiver == bidder
        assert settlement.asset_amount == accepted_bidder.quantity.native

        assert accepted_bidder.price == price
        assert accepted_bidder.quantity == quantity

        itxn.Payment(
            receiver=Txn.sender,
            amount=accepted_bidder.quantity.native * accepted_bidder.price.native,
        ).submit()

    @arc4.abimethod
    def retract(self) -> None:
        retracted_bidder = self.bidders[Txn.sender].copy()
        del self.bidders[Txn.sender]

        itxn.Payment(
            receiver=Txn.sender, amount=retracted_bidder.deposited.native
        ).submit()
