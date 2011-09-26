#!/usr/bin/env python

import sys

# API docs:
#   http://code.google.com/p/support/wiki/IssueTrackerAPIPython
import gdata.projecthosting.client
import gdata.projecthosting.data
import gdata.gauth
import gdata.client
import gdata.data
import atom.http_core
import atom.core



class PatchBot():
    client = gdata.projecthosting.client.ProjectHostingClient()

    # you can use mewes for complete junk testing
    #PROJECT_NAME = "mewes"
    PROJECT_NAME = "lilypond"

    username = None
    password = None

    def __init__(self):
        # both of these bail if they fail
        self.get_credentials()
        self.login()

    def get_credentials(self):
        # TODO: handle this better
        filename = "google.login"
        try:
            login_data = open(filename).readlines()
            self.username = login_data[0]
            self.password = login_data[1]
        except:
            print "Error: you must create a %s" % (filename),
            print "file containing your username and password"
            print "(one on each line)"
            sys.exit(1)

    def login(self):
        try:
            self.client.client_login(
                self.username, self.password,
                source='lilypond-patch-handler', service='code')
        except:
            print "Incorrect username or password"
            sys.exit(1)


    def create_issue(self, subject, description):
        """Create an issue."""
        return self.client.add_issue(
            self.PROJECT_NAME,
            "Patch: " + subject,
            description,
            self.username,
            labels = ["Type-Enhancement", "Patch-new"])

    def update_issue(self, issue_id, description):
        return self.client.update_issue(
            self.PROJECT_NAME,
            issue_id,
            self.username,
            comment = description,
            labels = ["Patch-new"])

    def find_fix_issue_id(self, text):
        splittext = text.split()
        issue_id = None
        # greedy search for the issue id
        for i, word in enumerate(splittext):
            if word == "fix" or word == "issue":
                try:
                    issue_id = int(splittext[i+1])
                    break
                except:
                    pass
        return issue_id

    def upload(self, issue, patchset, subject="", description=""):
        if not subject:
            subject = "new patch"
        description = description + "\n\n" + "http://codereview.appspot.com/" + issue
        # update or create?
        issue_id = self.find_fix_issue_id(subject+' '+description)
        if issue_id:
            self.update_issue(issue_id, description)
        else:
            self.create_issue(subject, description)
        return True


# hacky integration
def upload(issue, patchset, subject="", description=""):
    patchy = PatchBot()
    status = patchy.upload(issue, patchset, subject, description)
    if status:
        print "Tracker issue done"
    else:
        print "Problem with the tracker issue"


