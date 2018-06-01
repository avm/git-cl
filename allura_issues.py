#!/usr/bin/python
# Integrates git-cl with the Allura issue tracking tool
# Phil Holmes

import requests
import cl_settings
import sys

settings = cl_settings.Settings()

def create_issue(subject, description):
  BEARER_TOKEN = settings.GetToken()
  allura_server = settings.GetTrackerServer()
  allura_api = add_api_string(allura_server)

  data = {
    'access_token': BEARER_TOKEN,
    'ticket_form.summary': subject,
    'ticket_form.description': description,
    'ticket_form.status': 'Started',
    'ticket_form.custom_fields._patch': 'new',
    'ticket_form.custom_fields._type': 'Enhancement',
  }
  allura_result = requests.post(allura_api + "/new", data=data)
  if allura_result.ok:
    print 'Ticket created at: %s' % allura_result.url.replace("/rest","")
  else:
    print 'Error code %s' % allura_result.status_code
    print 'Failed URL was %s' % allura_api + "/new"
    print 'Failed data was %s' % data
    sys.exit(1)
  issue_id = get_issue_number(allura_result.url)

  # Now get text of issue back, to locate the originator
  filehandle = requests.get(allura_api + issue_id)
  if not filehandle.ok:
    print "Problem getting originator for Allura issue"
    sys.exit(1)

  issue_str = filehandle.content
  originator = get_reporter(issue_str)

  # Now set the owner to the originator
  data = {
    'access_token': BEARER_TOKEN,
    'ticket_form.assigned_to': originator,
  }

  filehandle = requests.post(allura_api + issue_id + "/save", data=data)
  if not filehandle.ok:
    print "Problem setting originator for Allura issue"
    sys.exit(1)

  return issue_id

def update_issue(allura_issue_id, description):
  BEARER_TOKEN = settings.GetToken()
  allura_server = settings.GetTrackerServer()
  allura_api = add_api_string(allura_server)

  # Set patch status to new
  data = {
    'access_token': BEARER_TOKEN,
    'ticket_form.status': 'Started',
    'ticket_form.custom_fields._patch': 'new',
  }

  filehandle = requests.post(allura_api + str(allura_issue_id) + "/save", data=data)
  if not filehandle.ok:
    print "Problem setting patch status for Allura issue"
    sys.exit(1)

  # Now get the thread ID so we can add a note to the correct thread
  filehandle = requests.get(allura_api + str(allura_issue_id))
  issue_data = filehandle.content
  thread_id = get_thread_ID(issue_data)
  data = {
    'access_token': BEARER_TOKEN,
    'text': description,
  }

  issue_id = get_issue_number(filehandle.url)

  allura_url = allura_api + "/_discuss/thread/"
  allura_url += thread_id + "/new"

  allura_result = requests.post(allura_url, data=data)
  if allura_result.ok:
    print 'Ticket %s updated' % allura_result.url
  else:
    print 'Update attempt returns error code %s' % (allura_result.status_code)
    sys.exit(1)
  return issue_id

def get_issue_number(url):
  trim_url = url[0:len(url)-1]
  slash_pos = trim_url.rfind('/')
  issue = url[slash_pos+1: len(url)]
  if issue[len(issue)-1] == '/':
    issue = issue [0:len(issue)-1]
  return issue

def add_api_string(allura_server):
  p_pos = allura_server.find('/p/')
  if p_pos < 1:
    print 'Allura server has unxepected format: expect it to contain /p/ in the URL'
    print 'Please run git cl config'
    sys.exit(1)
  api_server = allura_server[0:p_pos]
  api_server += '/rest'
  api_server += allura_server [p_pos:]
  return api_server

def get_reporter(issue_text):
  reporter_pos = issue_text.index('"reported_by": "')
  reporter_str = issue_text[reporter_pos+16:]
  quote_pos = reporter_str.index('"')
  reporter_str = reporter_str[0:quote_pos]
  return reporter_str

def get_thread_ID(issue_data):
  discussion_pos = issue_data.index('"discussion_thread": ')
  discussion_data = issue_data[discussion_pos:]
  id_data = discussion_data.index('"_id": ')
  thread_id = discussion_data[id_data+8:id_data+16]
  return thread_id

