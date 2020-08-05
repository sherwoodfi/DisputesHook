# from pprint import pprint
import boto3
import json
import os
import braintree
import datetime
import psycopg2 as pg
from psycopg2.extensions import AsIs

S3_WEBHOOK_STORAGE = os.environ["S3_WEBHOOK_STORAGE"]
S3_WEBHOOK_MALFORMED = os.environ["S3_WEBHOOK_MALFORMED"]
S3_WEBHOOK_ARCHIVE = os.environ["S3_WEBHOOK_ARCHIVE"]


def epoch_to_datetime(epochstamp):
    tstamp = datetime.datetime.fromtimestamp(epochstamp)
    return tstamp


def datetime_to_strftime(dtstamp):
    tstamp = dtstamp.strftime("%Y-%m-%d %H:%M:%S")
    return tstamp


def decimal_to_cents(deci):
    cents = int(deci * 100)
    return cents


def connect_to_db():
    # ! if deploying to aws lambda, use psycopg2 with a statically linked libpq.so
    # ! pip install aws-psycopg2
    conn = pg.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PW"],
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        database=os.environ["DB_NAME"],
    )

    return conn


def insert_dobj_into_db(dobj, conn):
    curr = conn.cursor()

    columns = dobj.keys()
    values = [dobj[column] for column in columns]

    insert_statement = "insert into public.disputes (%s) values %s"
    insert_statement = curr.mogrify(
        insert_statement, (AsIs(",".join(columns)), tuple(values))
    )

    try:
        curr.execute(insert_statement)
        conn.commit()
        return "success"
    except Exception as e:
        print(e)
        return "fail"


def create_s3_resource():
    aws_access_key_id = os.environ["aws_access_key_id"]
    aws_secret_access_key = os.environ["aws_secret_access_key"]

    s3 = boto3.resource(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name="us-west-2",
    )

    return s3


def move_s3_object(dispute_obj, target_bucket):
    s3 = create_s3_resource()
    copy_source = {"Bucket": S3_WEBHOOK_STORAGE, "Key": dispute_obj.key}
    s3.meta.client.copy(copy_source, target_bucket, dispute_obj.key)
    dispute_obj.delete()


def get_s3_disputes():
    s3 = create_s3_resource()
    dispute_bucket = s3.Bucket(S3_WEBHOOK_STORAGE)

    return dispute_bucket.objects.all()


def get_braintree_gateway():
    gateway = braintree.BraintreeGateway(
        braintree.Configuration(
            braintree.Environment.Production,
            merchant_id=os.environ["BT_MERCHANT_ID"],
            public_key=os.environ["BT_PUBLIC_KEY"],
            private_key=os.environ["BT_PRIVATE_KEY"],
        )
    )

    return gateway


def braintree_decode(dispute_obj, bt_gateway):
    webhook_notification = bt_gateway.webhook_notification.parse(
        str(dispute_obj["bt_signature"]), str(dispute_obj["bt_payload"])
    )
    return webhook_notification


def refactor_braintree_obj(dispute_obj):
    dobj = dispute_obj.dispute

    refactored_obj = {
        "source": "braintree",
        "id": dobj.id,
        "created_at": datetime_to_strftime(dobj.created_at),
        "disputed_at": datetime_to_strftime(dispute_obj.timestamp),
        "hook_event": dispute_obj.kind,  ## webhook event
        "event": dobj.kind,  ## dispute kind
        "status": dobj.status,
        "reason": dobj.reason,
        "reason_code": dobj.reason_code,
        "reason_description": dobj.reason_description,
        "currency": dobj.currency_iso_code,
        "amount": decimal_to_cents(dobj.amount),
        "amount_disputed": decimal_to_cents(dobj.amount_disputed),
        "amount_won": decimal_to_cents(dobj.amount_won),
        "respond_by": datetime_to_strftime(dobj.response_deadline),
        "case_number": dobj.case_number,
        "stripe_charge_id": None,
    }

    return refactored_obj


def refactor_stripe_obj(dispute_obj):
    dobj = dispute_obj["body"]["data"]["object"]
    balance_transactions = dobj["balance_transactions"][0]

    refactored_obj = {
        "source": "stripe",
        "id": dobj["id"],
        "created_at": epoch_to_datetime(dispute_obj["body"]["created"]),
        "disputed_at": epoch_to_datetime(dobj["created"]),
        "hook_event": dispute_obj["body"]["type"],
        "event": balance_transactions["type"],
        "status": dobj["status"],
        "reason": dobj["reason"],
        "reason_code": None,
        "reason_description": balance_transactions["description"],
        "currency": balance_transactions["currency"],
        "amount": dobj["amount"],
        "amount_disputed": balance_transactions["amount"],
        "amount_won": None,
        "respond_by": epoch_to_datetime(dobj["evidence_details"]["due_by"]),
        "case_number": dispute_obj["body"]["id"],
        "stripe_charge_id": dobj["charge"],
    }

    return refactored_obj


def route_dispute_objects(s3_disputes, bt_gateway):
    # create single connection to database
    conn = connect_to_db()

    # iterate over any object in s3
    for dispute in s3_disputes:
        obj = dispute.get()["Body"].read().decode()
        obj = json.loads(obj)

        # check object for keys associated with specific entity (braintree, stripe)
        if "bt_signature" in obj["body"].keys():
            webhook_notification = braintree_decode(obj["body"], bt_gateway)
            refactored_obj = refactor_braintree_obj(webhook_notification)
        elif "Stripe-Signature" in obj["headers"].keys():
            # route entity object to be refactored
            refactored_obj = refactor_stripe_obj(obj)
        else:
            move_s3_object(dispute, S3_WEBHOOK_MALFORMED)

        # upload refactored object to database
        response = insert_dobj_into_db(refactored_obj, conn)
        if response == "success":
            move_s3_object(dispute, S3_WEBHOOK_ARCHIVE)


def lambda_handler(event, context):
    s3_disputes = get_s3_disputes()
    bt_gateway = get_braintree_gateway()
    route_dispute_objects(s3_disputes, bt_gateway)


if __name__ == "__main__":
    s3_disputes = get_s3_disputes()
    bt_gateway = get_braintree_gateway()
    route_dispute_objects(s3_disputes, bt_gateway)

