#!/usr/bin/python
# Integrates git-cl with the Allura issue tracking tool
# Phil Holmes

import os
import sys
import subprocess
import urllib2
import textwrap

class Settings:
  def __init__(self):
    self.server = None
    self.tracker_server = None
    self.token = None
    self.cc = None
    self.root = None
    self.is_git_svn = None
    self.svn_branch = None
    self.tree_status_url = None
    self.viewvc_url = None

  def GetTrackerServer(self, error_ok=False):
    if not self.tracker_server:
      if not error_ok:
        error_message = ('You must configure your setup by running '
                         '"git cl config".')
        self.tracker_server = self._GetConfig('allura.tracker',
                                      error_message=error_message)
      else:
        self.tracker_server = self._GetConfig('allura.tracker', error_ok=True)
    return self.tracker_server

  def GetToken(self, error_ok=False):
    if not self.token:
      if not error_ok:
        error_message = ('You must configure your review setup by running '
                         '"git cl config".')
        self.token = self._GetConfig('allura.token',
                                      error_message=error_message)
      else:
        self.token = self._GetConfig('allura.token', error_ok=True)
    return self.token

  def GetServer(self, error_ok=False):
    if not self.server:
      if not error_ok:
        error_message = ('You must configure your review setup by running '
                         '"git cl config".')
        self.server = self._GetConfig('rietveld.server',
                                      error_message=error_message)
      else:
        self.server = self._GetConfig('rietveld.server', error_ok=True)
    return self.server

  def GetCCList(self):
    if self.cc is None:
      self.cc = self._GetConfig('rietveld.cc', error_ok=True)
    return self.cc

  def GetRoot(self):
    if not self.root:
      self.root = os.path.abspath(RunGit(['rev-parse', '--show-cdup']).strip())
    return self.root

  def GetIsGitSvn(self):
    """Return true if this repo looks like it's using git-svn."""
    if self.is_git_svn is None:
      # If you have any "svn-remote.*" config keys, we think you're using svn.
      self.is_git_svn = RunGit(['config', '--get-regexp', r'^svn-remote\.'],
                               exit_code=True) == 0
    return self.is_git_svn

  def GetSVNBranch(self):
    if self.svn_branch is None:
      if not self.GetIsGitSvn():
        raise "Repo doesn't appear to be a git-svn repo."

      # Try to figure out which remote branch we're based on.
      # Strategy:
      # 1) find all git-svn branches and note their svn URLs.
      # 2) iterate through our branch history and match up the URLs.

      # regexp matching the git-svn line that contains the URL.
      git_svn_re = re.compile(r'^\s*git-svn-id: (\S+)@', re.MULTILINE)

      # Get the refname and svn url for all refs/remotes/*.
      remotes = RunGit(['for-each-ref', '--format=%(refname)',
                        'refs/remotes']).splitlines()
      svn_refs = {}
      for ref in remotes:
        match = git_svn_re.search(RunGit(['cat-file', '-p', ref]))
        if match:
          svn_refs[match.group(1)] = ref

      if len(svn_refs) == 1:
        # Only one svn branch exists -- seems like a good candidate.
        self.svn_branch = svn_refs.values()[0]
      elif len(svn_refs) > 1:
        # We have more than one remote branch available.  We don't
        # want to go through all of history, so read a line from the
        # pipe at a time.
        # The -100 is an arbitrary limit so we don't search forever.
        cmd = ['git', 'log', '-100', '--pretty=medium']
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        for line in proc.stdout:
          match = git_svn_re.match(line)
          if match:
            url = match.group(1)
            if url in svn_refs:
              self.svn_branch = svn_refs[url]
              proc.stdout.close()  # Cut pipe.
              break

      if not self.svn_branch:
        raise "Can't guess svn branch -- try specifying it on the command line"

    return self.svn_branch

  def GetTreeStatusUrl(self, error_ok=False):
    if not self.tree_status_url:
      error_message = ('You must configure your tree status URL by running '
                       '"git cl config".')
      self.tree_status_url = self._GetConfig('rietveld.tree-status-url',
                                             error_ok=error_ok,
                                             error_message=error_message)
    return self.tree_status_url

  def GetViewVCUrl(self):
    if not self.viewvc_url:
      self.viewvc_url = self._GetConfig('rietveld.viewvc-url', error_ok=True)
    return self.viewvc_url

  def _GetConfig(self, param, **kwargs):
    return RunGit(['config', param], **kwargs).strip()

class Changelist:
  def __init__(self, branchref=None):
    # Poke settings so we get the "configure your server" message if necessary.
    settings.GetServer()
    self.branchref = branchref
    if self.branchref:
      self.branch = ShortBranchName(self.branchref)
    else:
      self.branch = None
    self.upstream_branch = None
    self.has_RietveldIssue = False
    self.has_TrackerIssue = False
    self.has_description = False
    self.RietveldIssue = None
    self.TrackerIssue = None
    self.description = None

  def GetBranch(self):
    """Returns the short branch name, e.g. 'master'."""
    if not self.branch:
      self.branchref = RunGit(['symbolic-ref', 'HEAD']).strip()
      self.branch = ShortBranchName(self.branchref)
    return self.branch

  def GetBranchRef(self):
    """Returns the full branch name, e.g. 'refs/heads/master'."""
    self.GetBranch()  # Poke the lazy loader.
    return self.branchref

  def GetUpstreamBranch(self):
    if self.upstream_branch is None:
      branch = self.GetBranch()
      upstream_branch = RunGit(['config', 'branch.%s.merge' % branch],
                               error_ok=True).strip()
      if upstream_branch:
        remote = RunGit(['config', 'branch.%s.remote' % branch]).strip()
        # We have remote=origin and branch=refs/heads/foobar; convert to
        # refs/remotes/origin/foobar.
        self.upstream_branch = upstream_branch.replace('heads',
                                                       'remotes/' + remote)

      if not self.upstream_branch:
        # Fall back on trying a git-svn upstream branch.
        if settings.GetIsGitSvn():
          self.upstream_branch = settings.GetSVNBranch()

      if not self.upstream_branch:
        DieWithError("""Unable to determine default branch to diff against.
Either pass complete "git diff"-style arguments, like
  git cl upload origin/master
or verify this branch is set up to track another (via the --track argument to
"git checkout -b ...").""")

    return self.upstream_branch

  def GetTrackerIssue(self):
    """Returns the Tracker issue associated with this branch."""
    if not self.has_TrackerIssue:
      CheckForMigration()
      issue = RunGit(['config', self._TrackerIssueSetting()], error_ok=True).strip()
      if issue:
        self.TrackerIssue = issue
      else:
        self.TrackerIssue = None
      self.has_TrackerIssue = True
    return self.TrackerIssue

  def GetRietveldIssue(self):
    if not self.has_RietveldIssue:
      CheckForMigration()
      issue = RunGit(['config', self._RietveldIssueSetting()], error_ok=True).strip()
      if issue:
        self.RietveldIssue = issue
      else:
        self.RietveldIssue = None
      self.has_RietveldIssue = True
    return self.RietveldIssue

  def GetRietveldURL(self):
    return RietveldURL(self.GetRietveldIssue())

  def GetTrackerURL(self):
    return TrackerURL(self.GetTrackerIssue())

  def GetDescription(self, pretty=False):
    if not self.has_description:
      if self.GetRietveldIssue():
        url = self.GetRietveldURL() + '/description'
        self.description = urllib2.urlopen(url).read().strip()
      self.has_description = True
    if pretty:
      wrapper = textwrap.TextWrapper()
      wrapper.initial_indent = wrapper.subsequent_indent = '  '
      return wrapper.fill(self.description)
    return self.description

  def GetPatchset(self):
    if not self.has_patchset:
      patchset = RunGit(['config', self._PatchsetSetting()],
                        error_ok=True).strip()
      if patchset:
        self.patchset = patchset
      else:
        self.patchset = None
      self.has_patchset = True
    return self.patchset

  def SetPatchset(self, patchset):
    """Set this branch's patchset.  If patchset=0, clears the patchset."""
    if patchset:
      RunGit(['config', self._PatchsetSetting(), str(patchset)])
    else:
      RunGit(['config', '--unset', self._PatchsetSetting()])
    self.has_patchset = False

  def SetTrackerIssue(self, issue):
    """Set this branch's Tracker issue.  If issue=0, clears the issue."""
    if issue:
      RunGit(['config', self._TrackerIssueSetting(), str(issue)])
    elif self.GetTrackerIssue():
      RunGit(['config', '--unset', self._TrackerIssueSetting()])
    self.has_TrackerIssue = False

  def SetRietveldIssue(self, issue):
    """Set this branch's Rietveld issue.  If issue=0, clears the issue."""
    if issue:
      RunGit(['config', self._RietveldIssueSetting(), str(issue)])
    else:
      RunGit(['config', '--unset', self._RietveldIssueSetting()])
      self.SetTrackerIssue(0)
      self.SetPatchset(0)
    self.has_RietveldIssue = False

  def CloseRietveldIssue(self):
    """Close the Rietveld issue associated with this branch."""
    def GetUserCredentials():
      email = raw_input('Email: ').strip()
      password = getpass.getpass('Password for %s: ' % email)
      return email, password

    rpc_server = upload.HttpRpcServer(settings.GetServer(),
                                      GetUserCredentials,
                                      host_override=settings.GetServer(),
                                      save_cookies=True)
    # You cannot close an issue with a GET.
    # We pass an empty string for the data so it is a POST rather than a GET.
    data = [("description", self.description),]
    ctype, body = upload.EncodeMultipartFormData(data, [])
    rpc_server.Send('/' + self.GetRietveldIssue() + '/close', body, ctype)

  def _TrackerIssueSetting(self):
    """Returns the git setting that stores the Tracker issue."""
    return 'branch.%s.googlecodeissue' % self.GetBranch()

  def _RietveldIssueSetting(self):
    """Returns the git setting that stores the Rietveld issue."""
    return 'branch.%s.rietveldissue' % self.GetBranch()

  def _PatchsetSetting(self):
    """Returns the git setting that stores the most recent Rietveld patchset."""
    return 'branch.%s.rietveldpatchset' % self.GetBranch()

def RunCommand(cmd, error_ok=False, error_message=None, exit_code=False,
               redirect_stdout=True):
  # Useful for debugging:
  # print >>sys.stderr, ' '.join(cmd)
  if redirect_stdout:
    stdout = subprocess.PIPE
  else:
    stdout = None
  proc = subprocess.Popen(cmd, stdout=stdout)
  output = proc.communicate()[0]
  if exit_code:
    return proc.returncode
  if not error_ok and proc.returncode != 0:
    DieWithError('Command "%s" failed.\n' % (' '.join(cmd)) +
                 (error_message or output))
  return output


def RunGit(args, **kwargs):
  cmd = ['git'] + args
  return RunCommand(cmd, **kwargs)

did_migrate_check = False
def CheckForMigration():
  """Migrate from the old issue format, if found.

  We used to store the branch<->issue mapping in a file in .git, but it's
  better to store it in the .git/config, since deleting a branch deletes that
  branch's entry there.
  """

  # Don't run more than once.
  global did_migrate_check
  if did_migrate_check:
    return

  gitdir = RunGit(['rev-parse', '--git-dir']).strip()
  storepath = os.path.join(gitdir, 'cl-mapping')
  if os.path.exists(storepath):
    print "old-style git-cl mapping file (%s) found; migrating." % storepath
    store = open(storepath, 'r')
    for line in store:
      branch, issue = line.strip().split()
      RunGit(['config', 'branch.%s.rietveldissue' % ShortBranchName(branch),
              issue])
    store.close()
    os.remove(storepath)
  did_migrate_check = True

def ShortBranchName(branch):
  """Convert a name like 'refs/heads/foo' to just 'foo'."""
  return branch.replace('refs/heads/', '')

def RietveldURL(issue):
  """Returns the Rietveld URL for a particular issue."""
  return 'https://%s/%s' % (settings.GetServer(), issue)

def TrackerURL(issue):
  return 'https://sourceforge.net/p/testlilyissues/issues/%s/' % issue

def DieWithError(message):
  print >>sys.stderr, message
  sys.exit(1)

settings=Settings()

