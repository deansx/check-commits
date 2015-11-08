check-commits
=========================

Introduction / Description
----------------------

check-commits retrieves commit information from a git repo and produces json
(and, optionally, CSV) that can be used elsewhere in the defect analysis
flow.

Command Line Usage
----------------------

USAGE:

    check-commits [path_to_repo] -[Hh][elp]

The script takes one optional argument which specifies the pathname to the
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
teams may not be annotating commit messages with information that readily
identifies the transactions as addressing a defect.  Therefore, the script
also has the ability to read a list of commit SHA-1's that identify commits
that address defects. The file format is straightforward, it's a simple text
file with each line containing exactly one 40 character SHA-1.  The script
looks in the current working directory for an optional file named:

    <repo_name>.dft

If this "helper" file is not readable, the program proceeds without the
additional information, which could result in some commits being incorrectly
tagged as not being associated with defect repair.

Repo Contents
----------------------

* **check-commits** - main executable script
* check_commits/ - library containing modules for import
* check_commits/check_commits.py - module containing most of the code
* check_commits/__init__.py
* chk-cmt-tst-commit-recs-ref.txt - reference file for testing
* chk-cmt-tst-ref.csv - reference file for testing
* chk-cmt-tst.dft - test file that marks some commits as defects
* chk.bsh - Check the results of the test
* install.bsh - temporary install script, until I get around to setting up PyPI
* .gitignore
* LICENSE



Installation
----------------------

check-commits currently supports
[Python 3.4](https://www.python.org/downloads/).
All testing and development was performed on Linux, your mileage on other
platforms may vary. Further, the temporary installation script will only work
in an environment that supports Bash scripting. Sorry about that. I'll do
a pip version ASAP. In the meantime, the installation steps for a Linux
environment are:

    git clone git@github.com:deansx/check-commits.git
    cd check-commits
    ./install.bsh

NOTE: You may need elevated priveledges to perform the install.

This script should put the command file into a directory that is in your
shell's PATH, and the library module(s) in a directory that is in your Python
installation's sys.path. You may need to modify it for your specific situation,
and you might need to run with elevated priviledges.


Support
----------------------

If you have any questions, problems, or suggestions, please submit an
[issue](../../issues)

License & Copyright
----------------------

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
