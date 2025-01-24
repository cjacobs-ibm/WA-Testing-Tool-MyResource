import json
from argparse import ArgumentParser
from ibm_watson import AssistantV1
from ibm_watson import AssistantV2
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator, BearerTokenAuthenticator
import dateutil.parser
import datetime
import time

DEFAULT_WCS_VERSION='2018-09-20'
DEFAULT_PAGE_SIZE=500
DEFAULT_NUMBER_OF_PAGES=20

def getAssistant(ARGS):
    iam_apikey=ARGS['iam_apikey']
    bearer_token=ARGS['bearer_token']
    url=ARGS['url']
    version=ARGS['version']

    '''Retrieve Watson Assistant SDK object'''
    authenticator = None
    if iam_apikey != None:
        authenticator = IAMAuthenticator(iam_apikey)
    else:
        authenticator = BearerTokenAuthenticator(bearer_token)

    if 'environment_id' in ARGS and ARGS['environment_id'] is not None:
        c = AssistantV2(
            version=version,
            authenticator=authenticator
        )
    else:
        c = AssistantV1(
            version=version,
            authenticator=authenticator
        )

    #c.set_disable_ssl_verification(True) #TODO: pass disable_ssl parameter here
    c.set_service_url(url)
    return c

# This function used by Jupyter notebooks only, which are based on using iam_apikey only
def getLogs(iam_apikey, url, workspace_id, filter, page_size_limit=DEFAULT_PAGE_SIZE, page_num_limit=DEFAULT_NUMBER_OF_PAGES, version=DEFAULT_WCS_VERSION, environment_id=None):
    '''Public API for script, connects to Watson Assistant and downloads all logs'''
    ARGS = {}
    ARGS['iam_apikey'] = iam_apikey
    ARGS['bearer_token'] = ''
    ARGS['url'] = url
    ARGS['workspace_id'] = workspace_id
    ARGS['filter'] = filter
    ARGS['page_limit'] = page_size_limit
    ARGS['number_of_pages'] = page_num_limit
    ARGS['version'] = version
    ARGS['environment_id'] = environment_id

    service = getAssistant(ARGS)
    return getLogsInternal(service, ARGS)

def getLogsInternal(assistant, ARGS):
    workspace_id = None
    if 'workspace_id' in ARGS:
        workspace_id = ARGS['workspace_id']
    
    assistant_id = None
    if 'environment_id' in ARGS:
        assistant_id = ARGS['environment_id']

    filter = ARGS['filter'] 
    page_size_limit = ARGS['page_limit']
    page_num_limit = ARGS['number_of_pages']
    
    '''Fetches `page_size_limit` logs at a time through Watson Assistant log API, a maximum of `page_num_limit` times, and returns array of log events'''
    cursor = None
    pages_retrieved = 0
    allLogs = []
    noMore = False

    while pages_retrieved < page_num_limit and noMore != True:
        if assistant_id is not None:
            #v2-based or actions
            output = assistant.list_logs(assistant_id=assistant_id, sort='-request_timestamp', filter=filter, page_limit=page_size_limit, cursor=cursor)
        elif workspace_id is None:
            #v1-style, all - requires a workspace_id, assistant id, or deployment id in the filter
            output = assistant.list_all_logs(sort='-request_timestamp', filter=filter, page_limit=page_size_limit, cursor=cursor)
        else:
            #v1-dialog
            output = assistant.list_logs(workspace_id=workspace_id, sort='-request_timestamp', filter=filter, page_limit=page_size_limit, cursor=cursor)

        #Hack for API compatibility between v1 and v2 of the API - v2 adds a 'result' property on the response.  v2 simplest form is list_logs().get_result()
        output = json.loads(str(output))
        if 'result' in output:
           logs = output['result']
        else:
           logs = output

        if 'pagination' in logs and len(logs['pagination']) != 0:
            cursor = logs['pagination'].get('next_cursor', None)
            #Do not DOS the list_logs function!
            time.sleep(3.0)
        else:
            noMore = True

        if 'logs' in logs:
           allLogs.extend(logs['logs'])
           pages_retrieved = pages_retrieved + 1
           print("Fetched {} log pages with {} total logs".format(pages_retrieved, len(allLogs)))
        else:
           return None

    #Analysis is easier when logs are in increasing timestamp order
    allLogs.reverse()

    return allLogs

def writeLogs(logs, output_file, output_columns="raw"):
    '''
    Writes log output to file system or screen.  Includes four modes:
    `raw`: logs are written in JSON format
    `all`: all log columns useful for intent training are written in CSV format
    `utterance`: only the `input.text` column is written (one per line)
    `transcript`: Alternating lines of "User" and "Watson" transcript

    '''
    file = None
    if output_file != None:
       file = open(output_file,'w')

       print("Writing {} logs to {}".format(len(logs), output_file))

    if 'raw' == output_columns:
       writeOut(file, json.dumps(logs,indent=2))
       if file is not None:
           file.close()
       return

    if 'all' == output_columns:
        writeOut(file, 'Utterance\tIntent\tConfidence\tDate\tLast Visited')

    for log in logs:
       utterance    = log['request' ]['input']['text']
       intent       = 'unknown_intent'
       confidence   = 0.0
       date         = 'unknown_date'
       last_visited = 'unknown_last_visited'
       response     = ''
       if 'response' in log and 'intents' in log['response'] and len(log['response']['intents'])>0:
          intent     = log['response']['intents'][0]['intent']
          confidence = log['response']['intents'][0]['confidence']
          dateStr    = log['request_timestamp']
          date       = dateutil.parser.parse(dateStr).strftime("%Y-%m-%d")
          if 'nodes_visited' in log['response']['output'] and len (log['response']['output']['nodes_visited']) > 0:
             last_visited = log['response']['output']['nodes_visited'][-1]

       if 'response' in log and 'output' in log['response'] and 'text' in log['response']['output'] and len(log['response']['output']['text'])>0:
          response   = log['response']['output']['text'][0]

       if 'all' == output_columns:
          output_line = '{}\t{}\t{}\t{}\t{}'.format(utterance, intent, confidence, date, last_visited)
       elif 'utterance' == output_columns:
          output_line = utterance
       else:
          output_line = f"User: {utterance}\nWatson: {response}"

       writeOut(file, output_line)

    if output_file != None:
       file.close()

def writeOut(file, message):
    if file != None:
        file.write(message + '\n')
    else:
        print(message)

def create_parser():
    parser = ArgumentParser(description='Extracts Watson Assistant logs from a given workspace')
    parser.add_argument('-c', '--output_columns', type=str, help='Which columns you want in output, either "utterance", "raw", or "all" (default is "raw")', default='raw')
    parser.add_argument('-o', '--output_file', type=str, help='Filename to write results to')
    parser.add_argument('-w', '--workspace_id', type=str, help='Workspace identifier, required for Dialog skills')
    parser.add_argument('-e', '--environment_id', type=str, help='Assistant environment identifier, required for Actions skills')
    parser.add_argument('-a', '--iam_apikey', type=str, help='Assistant service iam api key, required for IBM cloud')
    parser.add_argument('-b', '--bearer_token', type=str, help='Assistant service bearer token, required for Cloud Pak')
    parser.add_argument('-f', '--filter', type=str, required=True, help='Watson Assistant log query filter')
    parser.add_argument('-v', '--version', type=str, default=DEFAULT_WCS_VERSION, help="Watson Assistant version in YYYY-MM-DD form.")
    parser.add_argument('-n', '--number_of_pages', type=int, default=DEFAULT_NUMBER_OF_PAGES, help='Number of result pages to download (default is {})'.format(DEFAULT_NUMBER_OF_PAGES))
    parser.add_argument('-p', '--page_limit', type=int, default=DEFAULT_PAGE_SIZE, help='Number of results per page (default is {})'.format(DEFAULT_PAGE_SIZE))
    parser.add_argument('-l', '--url', type=str, default='https://gateway.watsonplatform.net/assistant/api',
                        help='URL to Watson Assistant. Ex: https://gateway-wdc.watsonplatform.net/assistant/api')

    return parser

if __name__ == '__main__':
   ARGS = create_parser().parse_args()

   service = getAssistant(vars(ARGS))
   logs    = getLogsInternal(service, vars(ARGS))
   writeLogs(logs, ARGS.output_file, ARGS.output_columns)
