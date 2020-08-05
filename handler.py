## this code works with serverless templates
# npm install -g serverless (install globally)
# run serveless with bash
# serverless create --template aws-python3 --name DisputesWebhook --path DisputesWebhook
# running the above will generate a .yml file

import json
import os
import sys
import boto3
import random
import string

S3_WEBHOOK_STORAGE = os.environ["S3_WEBHOOK_STORAGE"]
aws_access_key_id = os.environ["aws_access_key_id"]
aws_secret_access_key = os.environ["aws_secret_access_key"]

s3 = boto3.client(
    "s3",
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
)


# * generate a random string for the file name
def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = "".join(random.choice(letters) for i in range(length))
    result_file = "{}.txt".format(result_str)
    return result_file


# * lambda function which catches and stores any webhook data in an S3 bucket
def webhook(event, context):

    try:
        random_file_name = get_random_string(12)
        data = json.dumps(event)
        s3.put_object(Body=data, Bucket=S3_WEBHOOK_STORAGE, Key=random_file_name)
        response = {
            "statusCode": 200,
            "body": "",
        }
        if event["method"] == "POST":
            response["body"] = event["body"]
            return response
        else:
            response = {"statusCode": 400, "body": "No POST detected"}
            return response
    except Exception as e:
        print(e)
        return e

