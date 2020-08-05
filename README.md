# DisputesHook
Set up for a webhook endpoint and ETL focused on payment platform disputes

This tool was built to receive dispute data via webhook from any payment processing platform (Braintree, Stripe), 
and refactor it into a template dictionary and write it to a database.

## Webhook Endpoint
Built using [serverless](https://www.serverless.com/) template for python, and hosted on aws S3 + Lambda

```bash
> npm install -g serverless (install globally)
> serverless
> serverless create --template aws-python3 --name DisputesWebhook --path DisputesWebhook
```

Running the above will generate a *.yml* template file that can be modified. You will need to add AWS credentials 
to your local configuration, but afterwards the server can be deployed using 

```bash
sls deploy
```

The output of sls will tell you your endpoints.

## ETL / Parser
I recommend deploying this to AWS Lambda separate from the Webhook endpoint.

The above endpoint is designed to just store any JSON object received in an S3 bucket. The bucket ideally triggers an AWS
lambda function via cloudwatch, checking each object for key/values specific to a payment platform and routes them to a parser.
