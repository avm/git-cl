#!/usr/bin/env python

# API docs:
#   http://code.google.com/p/support/wiki/IssueTrackerAPIPython
import gdata.projecthosting.client
import gdata.projecthosting.data
import gdata.gauth
import gdata.client
import gdata.data
import atom.http_core
import atom.core

# TODO: handle this better
my_username = "percival.music.ca"
my_password = "hunter2"

def authenticating_client(client, username, password):
    return client.client_login(
        username,
        password,
        source='lilypond-patch-handler',
        service='code')


def create_issue(client, subject, description):
    """Create an issue."""
    return client.add_issue(
        "lilypond",
        "Patch: " + subject,
        description,
        my_username,
        labels=["Patch-new", "Type-Other"])
        # default to Other?

def upload(issue, patchset, subject="", description=""):
    client = gdata.projecthosting.client.ProjectHostingClient()
    # TODO: error checking
    authenticating_client(client, my_username, my_password)

    # TODO: check if existing patch via "fix 1234" or something
    # like that.
    if not subject:
        subject = "new patch"
    description = description + "\n\n" + "http://codereview.appspot.com/" + issue
    create_issue(client, subject, description)


