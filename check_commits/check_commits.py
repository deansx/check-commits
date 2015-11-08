"""check_commits.py retrieves commit information from a git repo and produces
json, and optionally CSV, that can be used elsewhere in the defect analysis
flow.

The primary entry point for this module is the check_commits() function. This
function takes one required argument, which specifies the pathname to the
repo that is to be analyzed. If the repo path is not specified, the current
working directory is used as the default.

The JSON formatted string generated as a result of running this script is
written to a file, in the current working directory, named:

    <repo_name>.json

Note that 'repo_name' is extracted from the repo itself, but will generally
be the leaf of the pathname to the repo.

The script also supports the option to produce a CSV file named:

    <repo_name>.csv

The generation of the CSV file is gated by the global variable: GEN_CSV

Although this script tries to use heuristics to determine which commits
correspond to defects, this tactic still requires refinement. Further, some
users may not be annotating commit messages with information that readily
identifies the transactions as addressing a defect.  Therefore, the script
also has the ability to read a list of commit SHA-1's that identify commits
that address defects. The file format is straightforward, it's a simple text
file with each line containing exactly one 40 character SHA-1.  The script
looks in the current working directory for an optional file named:

    <repo_name>.dft

If this "helper" file is not readable, the program proceeds without the
additional information, which could result in some commits being incorrectly
tagged as not being associated with defect repair.


Copyright 2015 Grip QA

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

__author__ = "Dean Stevens"
__copyright__ = "Copyright 2015, Grip QA"
__license__ = "Apache License, Version 2.0"
__status__ = "Prototype"
__version__ = "0.0.1"

import sys
import os
import subprocess
import argparse
import re
import json
import csv

from datetime import datetime
from datetime import timezone

# Gates whether we generate a CSV file of the result
GEN_CSV = True
# Gates whether we generate a plain text representation of the result
GEN_TEXT = True

FATAL_LBL = "FATAL ERROR: "
ERR_LBL = "ERROR: "
NOTE_LBL = "NOTE: "
EXIT_FAILURE = 1

class CommitRec(object):
    """Parses and holds the data from Git needed for defect analysis

    Attributes:
        repo - the name of the repo being analyzed
        timestamp - time of the commit
        commit - SHA-1 of the commit
        file - name of the file involved in the commit. Each commit will have
                one, or more, files associated with it.
        lines_added - number of lines added to the file as part of this commit
        lines_deleted - number of lines added to the file as part of this
                commit
        author - email address of the person responsible for the commit
        is_defect - whether the commit is associated with fixing a defect
    """
    __slots__ = [ "repo"
                 ,"timestamp"
                 ,"commit"
                 ,"file"
                 ,"lines_added"
                 ,"lines_deleted"
                 ,"author"
                 ,"is_defect"
                ]

    # Constants used for analysis
    GIT_DATE_FMT = '%a %b %d %H:%M:%S %Y %z'
    COMMIT_REGEX = re.compile("commit ([a-f0-9]{40})")
    AUTHOR_REGEX = re.compile("Author:\s+(.*)\s+<(.*)>")
    DATE_REGEX = re.compile("Date:\s+(.*)")
    FILE_REGEX = re.compile("(\d+)\t(\d+)\t(\S+)")
    DEFECT_REGEX = re.compile("JIRA-\d+")

    def __init__( self
                 ,repo
                 ,timestamp=0
                 ,commit=0
                 ,file=None
                 ,lines_added=-1
                 ,lines_deleted=-1
                 ,author=None
                 ,is_defect=False
                ):
        """Initialize the instance, generally, we're creating an almost
        empty object whose attributes will be filled in during analysis,
        so most of the parameters have defaults that signify, "not yet 
        assigned." The one exception is "repo" which must have the same
        value for every record in the run
        """
        self.repo          = repo
        self.timestamp     = timestamp
        self.commit        = commit
        self.file          = file
        self.lines_added   = lines_added
        self.lines_deleted = lines_deleted
        self.author        = author
        self.is_defect     = is_defect

    def is_file_line(line):
        """Checks the line to see if it matches a changes in file line
        NOTE: This is a class function, not an instance function, so no
              "self" argument.
        Args:
            line - str representing one line from the log
        Returns:
            True if the line is a log line that specifies file change
            information 
        """
        if CommitRec.FILE_REGEX.match(line) is None:
            retval = False
        else:
            retval = True
        return retval

    def is_commit_line(line):
        """Checks the line to see if it matches a commit line
        NOTE: This is a class function, not an instance function, so no
              "self" argument.
        Args:
            line - str representing one line from the log
        Returns:
            True if the line is a log line that specifies a commit heading
            with an apparent SHA-1
        """
        if CommitRec.COMMIT_REGEX.match(line) is None:
            retval = False
        else:
            retval = True
        return retval

    def parse_commit(self, line):
        """Parses the "commit SHA-1" line, if possible"

        If parsing fails, there's something seriously wrong with our
        logic, so we exit with a failure status.

        Args:
            line - the string containing a line from the log file that we
                    suspect is the start of a commit block
        """
        commit_match = self.COMMIT_REGEX.match(line)
        if commit_match is not None:
            # Separate the "commit" from the SHA-1, we're only interested
            # in the latter.
            self.commit = commit_match.group(1)
        else:
            fstr = "{0}Unable to extract commit info\n{1}In line: '{2}'\n"
            sys.stderr.write(fstr.format(FATAL_LBL, ' '*len(FATAL_LBL), line))
            sys.exit(EXIT_FAILURE)            

    def parse_timestamp(self, lines):
        """Searches the block of log lines looking for the date line and
        converts the date into a timestamp

        If parsing fails, there's something seriously wrong with our
        logic, so we exit with a failure status.

        Args:
            lines - the list of strings, each of which contains a line
                    from the log file that is part of the current commit
                    block
        Returns:
            The index into lines where the date was located, since we exit()
            if we don't find the timestamp, we don't have to worry about the
            return value for that case.
        """
        for idx,l in enumerate(lines):
            date_match = self.DATE_REGEX.match(l)
            if date_match is not None:
                date_str = date_match.group(1)
                dtime = datetime.strptime(date_str, self.GIT_DATE_FMT)
                self.timestamp = dtime.replace(tzinfo=timezone.utc).timestamp()
                break
        if date_match is None:
            # fstr = "{0}Unable to create timestamp from block:\n\n"
            # sys.stderr.write(fstr.format(FATAL_LBL, ' '*len(FATAL_LBL)))
            # fstr = "{0}{1}\n"
            # for l in lines:
            #     sys.stderr.write(fstr.format(' '*(len(FATAL_LBL)+4), l))
            self._block_fail("Unable to create timestamp from", lines)
            sys.exit(EXIT_FAILURE)
        return idx

    def parse_file(self, line):
        """Parses a file line and extracts the filename, lines added/deleted
        
        Each commit will have one, or more files associated with it. For
        each file, we'll extract the name of the file, the number of lines
        added to the file in the commit and the number of lines deleted from
        the file in the commit.

        If parsing fails, there's something seriously wrong with our
        logic, so we exit with a failure status.

        Args:
            line - the string containing a line from the log file that we
                    suspect contains the date of the commit
        """
        file_match = self.FILE_REGEX.match(line)
        if file_match is not None:
            self.lines_added = int(file_match.group(1))
            self.lines_deleted = int(file_match.group(2))
            self.file = file_match.group(3)
        else:
            fstr = "{0}Unable to parse file changes\n{1}In line: '{2}'\n"
            sys.stderr.write(fstr.format(FATAL_LBL, ' '*len(FATAL_LBL), line))
            sys.exit(EXIT_FAILURE)
    
    def parse_author(self, lines):
        """Searches the block of log lines looking for the author line and
        retrieves the email id of the committer

        If parsing fails, there's something seriously wrong with our
        logic, so we exit with a failure status.

        Args:
            lines - the list of strings, each of which contains a line
                    from the log file that is part of the current commit
                    block
        """
        for l in lines:
            author_match = self.AUTHOR_REGEX.match(l)
            if author_match is not None:
                self.author = author_match.group(2)
                break
        if author_match is None:
            self._block_fail("Unable to identify author in", lines)
            sys.exit(EXIT_FAILURE)   

    def parse_msg(self, lines, defect_commits):
        """Parses the commit message line(s), and attempts to determine
        whether this commit represents an effort to address a defect.

        If the user has identified this commit as being associated with a
        defect we follow their guidance. Otherwise, we attempt to identify
        commits related to addressing a defect by looking for clues in the
        commit message.

        Args:
            line - the string containing a line from the log file that we
                    suspect contains the date of the commit
            defect_commit - object that manages a collection of commits that
                    the user has told us are associated with defect fixes.
                    May be empty.
        """

        if defect_commits.is_defect(self.commit):
            # Tagged by the user
            self.is_defect = True
        else:
            # Otherwise, join all of the commit message strings together
            # and attempt to find clues that this commit addressed a
            # defect
            msg_str = ''.join(lines)
            if self.DEFECT_REGEX.search(msg_str) is not None:
                #print("Defect Message was: " + msg_str)
                self.is_defect = True
            else:
                self.is_defect = False

    def __repr__(self):
        """Produce a string representation of this object.
        In this case, we'll produce something that approximates a JSON
        formatted string - sort of like the textual representation of
        a Python dictionary.

        Returns:
            A string containing the representation of this object
        """
        def prep(k):
            """ Prepare a text representation of an attribute / value pair

            Given an attribute of this object, retrieve the corresponding
            value and format them appropriately as a JSON like string
            {"key":value} or {"key":"value"}

            We format the value differently if it's a str, a number, or
            a bool

            Args:
                k - the attribute, we're treating it like a key
            Returns:
                A string containing the properly formatted attr/value pair
            """
            fstr = '"{0}":{1}'
            qstr = '"{0}":"{1}"'
            v = getattr(self, k)
            if type(v) is str:
                ret_str = qstr.format(k, v)
            elif type(v) is int or type(v) is float:
                ret_str = fstr.format(k, v)
            elif type(v) is bool:
                ret_str = fstr.format(k, "true" if v else "false")
            else:
                ret_str = fstr.format(k, v)
            return ret_str

        # We'll collect the attribute/value pairs into a string and join
        # the entries together after they're all generated
        outp = []
        for k in self.__slots__:
            outp.append(prep(k))
                
        return ''.join(["{", ','.join(outp), "}"])

    def to_dict(self):
        """Produce a Python dictionary representation of this object
        
        Since we used __slots__, we have to hand code the dictionary
        form.  We need a dictionary form to generate the JSON and CSV

        Returns:
            A dictionary containing the attribute/value pairs contained in
            this object
        """
        od = {}
        for k in self.__slots__:
            od[k] = getattr(self, k)
        return od

    def clone(self):
        """Create a new object to represent additional files from this commit

        If a commit contains multiple files, we'll need multiple CommitRec
        objects to fully represent the commit.  After the first CommitRec is
        populated, most of the data fields are the same for subsequen
        CommitRec objects, except the file specific data (file name, lines
        added, lines deleted).

        This function creates a new CommitRec instance with the same
        attribute values as the source object, with the exceptions listed
        above.

        Returns:
            A new CommitRec object with most of the information the same
            as this object, with the exceptions listed above.
        """
        return CommitRec( self.repo
                         ,self.timestamp
                         ,self.commit
                         ,author=self.author
                         ,is_defect=self.is_defect
                        )

    def _block_fail(self, msg, lines):
        """Generates a fatal error message that includes the failing log block

        Args:
            msg - str with the message that explains the failure
            lines - list of lines from the log file where the failure occurred
        """
        fstr = "{0}{1} block:\n\n"
        sys.stderr.write(fstr.format(FATAL_LBL, msg))
        fstr = "{0}{1}\n"
        for l in lines:
            sys.stderr.write(fstr.format(' '*(len(FATAL_LBL)+4), l))


class CommitRecEncoder(json.JSONEncoder):
    """Overrides the default JSON encoder to allow us to encode the
    CommitRec object
    """
    def default(self, obj):
        if isinstance(obj, CommitRec):
            return obj.to_dict()
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


class DefectCommits(object):
    """Manages the external list of commits that are related to defects
    
    Reads the file containing the commits (listed one per line in the file)
    that are related to fixing a defect and maintains them in an internal
    collection. These are used, in addition to the built in heuristics to
    identify commits that were made to address a defect.

    Also provides an interface for checking a given commit SHA-1 against the
    internal collection.

    Attributes:
        defect_commits - the collection of SHA-1's that this object manages
    """
    __slots__ = ["defect_commits"]

    def __init__(self, defects_file):
        """Attempts to open/read the file of commits and retains the results

        Args:
           defects_file - pathname to the file containing the externally 
                            provided collection of commits
        """
        self.defect_commits = set()
        try:
            with open(defects_file, 'r') as f:
                for l in f:
                    self.defect_commits.add(l.rstrip())
        except FileNotFoundError:
            sys.stdout.write(NOTE_LBL + 
                             "No external defect commits specified.\n"
                            )
        except PermissionError:
            sys.stdout.write(NOTE_LBL + 
                             ("Unable to open external defect commits file. "
                              "Will use internal heuristics.\n")
                            )
    
    def is_defect(self, commit):
        """ Checks the internal collection of commits for a match
        Args:
            commit - str containing the SHA-1 to check
        Returns
            True if the specified commit is in the internal collection, which
            signifies that the commit is associated with fixing a defect
        """
        return True if commit in self.defect_commits else False


def find_commits(log):
    """Generates a list of indices for the start of each commit block
    
    Searches the log for "commit SHA-1" lines, which start a block of
    information about a specific commit. The indices of these commit block
    starts are returned in a new list

    Args:
        log - list of strs that contains the contents of the git log
    Returns:
        List of indices into the log, each of which is the position of
        the beginning of a commit block in the log.
    """
    return [l for l,x in enumerate(log) 
            if CommitRec.COMMIT_REGEX.match(x) is not None]


def proc_commits(log, commits, repo_name):
    """Process the git log and extracts the information that we need.

    We process the log in chunks, each of which represents a single commit.
    From each block, we parse out the information that we're interested in
    and create one instiance of the CommitRec object for each file involved
    in each commit.

    Args:
        log - list of lines of text generated by the git log --numstat command
        commits - list of indices into the log list. Each element of this
                    list points to the starting element of a commit's
                    information in the log
        repo_name - str containing the name of the repo that we're processing
    Returns:
        The list of CommitRec ojbects that were generated during processing
    """

    # List to accumulate the CommitRec objects generated
    commit_recs = []

    # Initialize the object that may (if the user has provided it) contain
    # the commit SHA-1's that are associated with fixing a defect. We'll use
    # this to "cheat" a bit, in cases where our heuristics for determing which
    # commits relate to defects is less than completely effective, perhaps
    # due to insufficient information in the log
    defect_commits = DefectCommits(repo_name+".dft")

    def parse_block(lines):
        """Parses a block from the git log that represents a single commit.

        The caller has chopped up the log into blocks of lines that each
        represents a single commit. A commit will have the SHA-1, the Author,
        the time, the commit message, the files involved and the number of
        lines added/deleted for each file.

        This function creates the CommitRec(s - plural if the commit involved
        more than one file, we'll create a separate CommitRec object for each
        file). Then uses the CommitRec object's functions to actually parse,
        and store the information we're extracting.

        Args:
            lines - list of strings each of which represents a line from
                    the git log
        Returns:
            List of the CommitRec object(s) - one for each file involved in
            the commit.
        """
        # Initialize the first CommitRec object
        commit_rec = CommitRec(repo_name)

        # Parse the block of lines to extract the commit SHA-1, since this
        # is a block of commits, the record should be the first one in
        # the block
        commit_rec.parse_commit(lines[0])
        # For author & timestamp, we can't rely on a fixed offset,
        # so the parse functions take most of the block
        commit_rec.parse_author(lines[1:])
        ts_idx = commit_rec.parse_timestamp(lines[1:])

        # The number of lines in the commit message and file segments of
        # the commit block are variable, so we can't use fixed offsets, 
        # other than the start of the commit message segment.  However,
        # since we know that the rest of the block only contains commit
        # message text, blank lines and file information, we walk through
        # the rest of the block and group everything into two buckets:
        #   msgs - holds commit messages and blan lines
        #   files - holds the text that identifies files and the number of
        #           lines changed in each
        msgs = []
        files = []
        # We slice the block of commit log entries so that we're only
        # dealing with the sections that contain either commit messages, or
        # file data
        #for l in lines[(ts_idx+1):len(lines)]:
        for l in lines[(ts_idx+1):]:
            if CommitRec.is_file_line(l):
                files.append(l)
            else:
                msgs.append(l)

        # Will hold the new CommitRec objects that we create in this pass
        new_commit_recs = []

        # Some commits, like merges, may not have any files, and, therefore,
        # no lines_added / lines_deleted information associated with them. We
        # currently only generate CommitRec data for commits that do have
        # files. This could change later...

        if files:
            # The message lines can be handled as a group.
            commit_rec.parse_msg(msgs, defect_commits)

            # Extract the information from the first (and perhaps only) file
            # line and initialize the list of CommitRec objects with this one
            # as the first element
            commit_rec.parse_file(files[0])
            new_commit_recs.append(commit_rec)

            # Loop through the remaining lines, if there are any to parse 
            # additional file lines related to this commit
            # We just took care of position 0, above
            idx = 1
            while idx < len(files):
                # clone commit_rec, add the information from the next line, and
                # finally, add the nxt_file object to the list of commit_rec(s)
                nxt_file = commit_rec.clone()
                nxt_file.parse_file(files[idx])
                new_commit_recs.append(nxt_file)
                idx += 1
        
        return new_commit_recs
    # end of parse_block()

    # Using the locations of the commit lines that we received as an argument,
    # We extract slices of the list that go from the location of each commit
    # in the log to the location just before the next commit - remember, 
    # slices do not include the upper bound.
    # Then we parse each slice, and, finally, extend the list of CommitRec
    # objects by the list returned from parse_block()
    for i in range(0,len(commits)-1):
        new_recs = parse_block(log[commits[i]:commits[i+1]])
        commit_recs.extend(new_recs)

    return commit_recs


def process_commits(repo_path):
    """Main function to process a Git repo

    Retrieves commit information from a Git repo. This function coordinates
    the other activities in the script that include identifying files and 
    contributors involved in the change as well as attempting to determine
    whether the commit was intended to address a defect.  Finally, generates
    the desired output files

    Args:
        repo_path - str with the filesystem pathname to the repo that is to 
                    be processed
    """
    # Get the name of the repo from the target repo itself by using:
    # git rev-parse --show-toplevel, then getting the leaf name of the
    # repo
    cmd_root = ["git", "-C",  repo_path]
    cmd = cmd_root + ["rev-parse", "--show-toplevel"]
    full_repo_name = subprocess.check_output(cmd).decode("utf-8").rstrip()
    repo_name = os.path.basename(full_repo_name)
    
    # The information that we deal with all comes from git log --numstat
    cmd = ["git", "-C", repo_path, "log", "--numstat"]
    log = subprocess.check_output(cmd).decode("utf-8").splitlines()

    # Get indices into the returned log for the start of each commit block
    commits = find_commits(log)
    # Add a dummy entry at the end that is one element beyond the end of the
    # log. We'll use this as an upper bound for processing
    commits.append(len(log)+1)

    # Does the actual processing of the log and generates a list of
    # "CommitRec" objects, each of which represents a file involved in a
    # commit.
    commit_files = proc_commits(log, commits, repo_name)

    # for c in commit_files:
    #     print(c)

    # Generate the JSON
    with open(''.join(["./", repo_name, ".json"]), 'w') as f:
        json.dump(commit_files,f, cls=CommitRecEncoder)

    # Optionally, generate the CSV
    if GEN_CSV:
        with open(''.join(["./", repo_name, ".csv"]), 'w', newline='') as f:
            writer = csv.DictWriter( f
                                    ,fieldnames=CommitRec.__slots__
                                    ,lineterminator=os.linesep
                                   )
            writer.writeheader()
            for c in commit_files:
                writer.writerow(c.to_dict())

    # Optionally, generte a text representation of the CommitRec dictionaries
    if GEN_TEXT:
        with open(''.join(["./", repo_name, "-commit-recs.txt"]), 'w') as f:
            for c in commit_files:
                f.write("{}\n".format(c))

