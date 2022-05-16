import asyncio
import base64
import json
from algosdk.future import transaction
from algosdk.future.transaction import PaymentTxn, AssetTransferTxn, AssetConfigTxn
from algosdk import account, mnemonic, logic
from algosdk.v2client import algod
from pyteal import *


algod_address = "http://localhost:4001"
algod_token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


computer_mnemonic = "december giggle gown trap bread soccer sort song judge island lift black bitter ghost impulse rice actress because ribbon unusual negative lucky monster above used"
user_mnemonic = "amused burger uphold hurt stereo holiday summer inherit believe angry token pledge chicken blush repeat patrol common hungry hello hammer humor ski coach above flight"
recycler_mnemonic = "welcome explain vast blind praise oak fire brush wreck jazz family sweet civil dynamic dance aim arrange bachelor flower earn brother pig giant absent digital"

computer_add = mnemonic.to_public_key(computer_mnemonic)
user_add = mnemonic.to_public_key(user_mnemonic)
recycler_add = mnemonic.to_public_key(recycler_mnemonic)


computer_key = mnemonic.to_private_key(computer_mnemonic)
user_key = mnemonic.to_private_key(user_mnemonic)
recycler_key = mnemonic.to_private_key(recycler_mnemonic)


def approval_program(recyclers):
    on_creation = Seq([
        App.globalPut(Bytes("User"), Global.zero_address()),
        App.globalPut(Bytes("Recycler1"), Addr(recyclers[0])),
        App.globalPut(Bytes("Recycler2"), Addr(recyclers[1])),
        App.globalPut(Bytes("Recycler3"), Addr(recyclers[2])),
        App.globalPut(Bytes("Recycler4"), Addr(recyclers[3])),
        App.globalPut(Bytes("Recycler5"), Addr(recyclers[4])),
        Return(Int(1))
    ])

    handle_optin = Return(Int(0))

    handle_closeout = Return(Int(0))

    handle_updateapp = Return(Int(0))

    handle_deleteapp = Return(Int(0))

    scratchCount = ScratchVar(TealType.uint64)

    handle_noop = Return(Int(1))

    @ Subroutine(TealType.none)
    def opt_in():
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_receiver: Global.current_application_address(),
                TxnField.asset_amount: Int(0),
                TxnField.xfer_asset: Txn.assets[i.load()],
            }),
            InnerTxnBuilder.Submit())

    i = ScratchVar(TealType.uint64)
    len = ScratchVar(TealType.uint64)

    release_clause = Or(
        App.globalGet(Bytes("Recycler1")) == Txn.accounts[2],
        App.globalGet(Bytes("Recycler2")) == Txn.accounts[2],
        App.globalGet(Bytes("Recycler3")) == Txn.accounts[2],
        App.globalGet(Bytes("Recycler4")) == Txn.accounts[2],
        App.globalGet(Bytes("Recycler5")) == Txn.accounts[2])

    init = Seq(
        For(i.store(Int(0)), i.load() < Txn.assets.length(), i.store(i.load() + Int(1))).Do(
            opt_in()
        ),

        Return(Int(1)))

    release = Seq([InnerTxnBuilder.Begin(), InnerTxnBuilder.SetFields({
        TxnField.type_enum: TxnType.Payment,
        TxnField.amount: Int(0),
        TxnField.receiver: Txn.accounts[0],
        TxnField.rekey_to: Txn.accounts[2]

    }), InnerTxnBuilder.Submit(),  Return(Int(1))])

    set_user = Seq([App.globalPut(Bytes("User"),
                                  Txn.accounts[1]), Return(Int(1))])

    Global.creator_address()

    handle_noop = Cond(
        [And(
            Global.group_size() == Int(1),
            Txn.application_args[0] == Bytes("Init")
        ), init],
        [And(
            Global.group_size() == Int(1),
            Txn.application_args[0] == Bytes("Release"),
            release_clause,
            Txn.sender() == App.globalGet(Bytes("User")),
        ), release],
        [And(
            Global.group_size() == Int(1),
            App.globalGet(Bytes("User")) == Global.zero_address(),
            Txn.sender() == Global.creator_address(),
            Txn.application_args[0] == Bytes("Set user"),

        ), set_user],
    )

    # default transaction sub-types for application
    program = Cond(
        [Txn.application_id() == Int(0), on_creation],
        [Txn.on_completion() == OnComplete.OptIn, handle_optin],
        [Txn.on_completion() == OnComplete.CloseOut, handle_closeout],
        [Txn.on_completion() == OnComplete.UpdateApplication, handle_updateapp],
        [Txn.on_completion() == OnComplete.DeleteApplication, handle_deleteapp],
        [Txn.on_completion() == OnComplete.NoOp, handle_noop]
    )

    return compileTeal(program, Mode.Application, version=6)


def clear_state_program():
    program = Return(Int(1))
    # Mode.Application specifies that this is a smart contract
    return compileTeal(program, Mode.Application, version=6)


def compile_program(client, source_code):
    compile_response = client.compile(source_code)
    return base64.b64decode(compile_response['result'])


def create_app(client, private_key, approval_program, clear_program, global_schema, local_schema):
    sender = account.address_from_private_key(private_key)

    on_complete = transaction.OnComplete.NoOpOC.real

    params = client.suggested_params()

    txn = transaction.ApplicationCreateTxn(sender, params, on_complete,
                                           approval_program, clear_program,
                                           global_schema, local_schema)

    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    client.send_transactions([signed_txn])

    try:
        transaction_response = transaction.wait_for_confirmation(
            client, tx_id, 5)
        print("TXID: ", tx_id)
        print("Result confirmed in round: {}".format(
            transaction_response['confirmed-round']))

    except Exception as err:
        print(err)
        return

    # display results
    transaction_response = client.pending_transaction_info(tx_id)
    app_id = transaction_response['application-index']
    print("Created new app-id:", app_id)

    return app_id


def deploy_new_application(algod_client, creator_private_key, compiled_teal, compiled_clear_teal):

    local_ints = 0
    local_bytes = 0
    global_ints = 1
    global_bytes = 16
    global_schema = transaction.StateSchema(global_ints, global_bytes)
    local_schema = transaction.StateSchema(local_ints, local_bytes)

    with open("./approval.teal", "w") as f:
        approval_program_teal = compiled_teal
        f.write(approval_program_teal)

    with open("./clear.teal", "w") as f:
        clear_state_program_teal = compiled_clear_teal
        f.write(clear_state_program_teal)

    approval_program_compiled = compile_program(
        algod_client, approval_program_teal)

    clear_state_program_compiled = compile_program(
        algod_client, clear_state_program_teal)

    print("--------------------------------------------")
    print("Deploying application......")

    app_id = create_app(algod_client, creator_private_key, approval_program_compiled,
                        clear_state_program_compiled, global_schema, local_schema)

    return app_id


def call_app(client, public_key, private_key, app_id, args, assets=[]):

    params = client.suggested_params()

    txn = transaction.ApplicationNoOpTxn(
        public_key, params, app_id, app_args=args, foreign_assets=assets, accounts=[user_add, recycler_add])

    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()

    client.send_transactions([signed_txn])

    try:
        transaction_response = transaction.wait_for_confirmation(
            client, tx_id, 4)
        print("TXID: ", tx_id)
        print("Result confirmed in round: {}".format(
            transaction_response['confirmed-round']))

    except Exception as err:
        print(err)
        return
    print("Application called")


def get_private_key_from_mnemonic(mn):
    private_key = mnemonic.to_private_key(mn)
    return private_key


def algo_transaction(add, key, amount, reciver, algod_client) -> dict:

    params = algod_client.suggested_params()
    unsigned_txn = PaymentTxn(
        add, params, reciver, amount)
    signed = unsigned_txn.sign(key)
    tx_id = algod_client.send_transaction(signed)
    pmtx = transaction.wait_for_confirmation(algod_client, tx_id, 5)
    return pmtx


def call_contract(app_id, args, private_key, public_key, assets=[]):
    algod_client = algod.AlgodClient(algod_token, algod_address)
    call_app(algod_client, public_key=public_key, app_id=app_id,
             private_key=private_key, args=[args], assets=assets)


def send_asset(algod_client, asset_id, asset_sender, asset_reciver, sender_private_key):
    params = algod_client.suggested_params()

    txn = AssetTransferTxn(
        sender=asset_sender,
        sp=params,
        receiver=asset_reciver,
        amt=1,
        index=asset_id)
    stxn = txn.sign(sender_private_key)
    try:
        txid = algod_client.send_transaction(stxn)
        print("Signed transaction with txID: {}".format(txid))
        confirmed_txn = transaction.wait_for_confirmation(
            algod_client, txid, 4)
        print("TXID: ", txid)
        print("Result confirmed in round: {}".format(
            confirmed_txn['confirmed-round']))

    except Exception as err:
        print(err)


def create_asset(algod_client, creator_public_key, manager_public_key, creator_private_key, asset_name, unit_name, total_supply):
    params = algod_client.suggested_params()

    txn = AssetConfigTxn(
        sender=creator_public_key,
        sp=params,
        total=total_supply,
        default_frozen=False,
        unit_name=unit_name,
        asset_name=asset_name,
        manager=manager_public_key,
        reserve=manager_public_key,
        freeze=manager_public_key,
        clawback=manager_public_key,
        url="",
        decimals=0)

    stxn = txn.sign(creator_private_key)

    try:
        txid = algod_client.send_transaction(stxn)
        print("Signed transaction with txID: {}".format(txid))
        confirmed_txn = transaction.wait_for_confirmation(
            algod_client, txid, 4)
        print("TXID: ", txid)
        print("Result confirmed in round: {}".format(
            confirmed_txn['confirmed-round']))

    except Exception as err:
        print(err)

    print("Transaction information: {}".format(
        json.dumps(confirmed_txn, indent=4)))

    try:

        ptx = algod_client.pending_transaction_info(txid)
        asset_id = ptx["asset-index"]

        return asset_id
    except Exception as e:
        print(e)


async def get_address(app_id):
    return logic.get_application_address(app_id)


async def main():
    algod_client = algod.AlgodClient(algod_token, algod_address)

    clear_state = clear_state_program()
    approval = approval_program([mnemonic.to_public_key(recycler_mnemonic), mnemonic.to_public_key(recycler_mnemonic), mnemonic.to_public_key(
        recycler_mnemonic), mnemonic.to_public_key(recycler_mnemonic), mnemonic.to_public_key(recycler_mnemonic), mnemonic.to_public_key(recycler_mnemonic)])

    app_id = deploy_new_application(
        algod_client, computer_key, approval, clear_state)

    app_add = await get_address(app_id=app_id)
    print(app_add)

    asset_id = create_asset(creator_public_key=computer_add, creator_private_key=computer_key,
                            asset_name="KascheCoin", unit_name="KC1", algod_client=algod_client, manager_public_key=computer_add,
                            total_supply=1)

    asset_id1 = create_asset(creator_public_key=computer_add, creator_private_key=computer_key,
                             asset_name="KascheCoin", unit_name="KC2", algod_client=algod_client, manager_public_key=computer_add,
                             total_supply=1)

    asset_id2 = create_asset(creator_public_key=computer_add, creator_private_key=computer_key,
                             asset_name="KascheCoin", unit_name="KC3", algod_client=algod_client, manager_public_key=computer_add,
                             total_supply=1)

    algo_transaction(add=computer_add, key=computer_key,
                     reciver=app_add, amount=1000000, algod_client=algod_client)
    call_contract(app_id=app_id, args="Init", assets=[asset_id, asset_id1, asset_id2],
                  private_key=computer_key, public_key=computer_add)
    send_asset(algod_client=algod_client, asset_id=asset_id, asset_sender=computer_add,
               asset_reciver=app_add, sender_private_key=computer_key)
    send_asset(algod_client=algod_client, asset_id=asset_id1, asset_sender=computer_add,
               asset_reciver=app_add, sender_private_key=computer_key)
    send_asset(algod_client=algod_client, asset_id=asset_id2, asset_sender=computer_add,
               asset_reciver=app_add, sender_private_key=computer_key)
    call_contract(app_id=app_id, args="Set user",
                  private_key=computer_key, public_key=computer_add)
    # call_contract(app_id=app_id, args="Set user",
    #               private_key=computer_key, public_key=computer_add)
    call_contract(app_id=app_id, args="Release",
                  public_key=user_add, private_key=user_key)
    # call_contract(app_id=app_id, args="Release",
    #               public_key=user_add, private_key=user_key)
    send_asset(algod_client=algod_client, asset_id=asset_id, asset_reciver=computer_add,
               asset_sender=app_add, sender_private_key=recycler_key)
    send_asset(algod_client=algod_client, asset_id=asset_id1, asset_reciver=computer_add,
               asset_sender=app_add, sender_private_key=recycler_key)
    send_asset(algod_client=algod_client, asset_id=asset_id2, asset_reciver=computer_add,
               asset_sender=app_add, sender_private_key=recycler_key)

    return app_id


asyncio.run(main())
