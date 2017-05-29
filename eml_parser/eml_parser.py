# -*- coding: utf-8 -*-
# pylint: disable=line-too-long

"""eml_parser serves as a python module for parsing eml files and returning various
information found in the e-mail as well as computed information.
"""

#
# Georges Toth (c) 2013-2014 <georges@trypill.org>
# GOVCERT.LU (c) 2013-2017 <info@govcert.etat.lu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
# Functionality inspired by:
#   https://github.com/CybOXProject/Tools/blob/master/scripts/email_to_cybox/email_to_cybox.py
#   https://github.com/iscoming/eml_parser/blob/master/eml_parser.py
#
# Regular expressions and subject field decoding inspired by:
#   "A Really Ruby Mail Library" - https://github.com/mikel/mail (MIT)
#
# Known issues:
#  - searching for IPs in the e-mail header sometimes leads to false positives
#    if a mail-server (e.g. exchange) uses an ID which looks like a valid IP
#

import sys
import email
import email.message
import email.policy
import email.utils
import re
import uuid
import datetime
import base64
import hashlib
import collections
import urllib.parse
import typing
import dateutil.parser
import eml_parser.decode

try:
    import magic
except ImportError:
    magic = None


__author__ = 'Toth Georges, Jung Paul'
__email__ = 'georges@trypill.org, georges.toth@govcert.etat.lu'
__copyright__ = 'Copyright 2013-2014 Georges Toth, Copyright 2013-2017 GOVCERT Luxembourg'
__license__ = 'AGPL v3+'


# regex compilation
# W3C HTML5 standard recommended regex for e-mail validation
email_regex = re.compile(r'''([a-zA-Z0-9.!#$%&'*+-/=?\^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*)''', re.MULTILINE)
#                 /^[a-zA-Z0-9.!#$%&'*+-/=?\^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$/
recv_dom_regex = re.compile(r'''(?:(?:from|by)\s+)([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]{2,})+)''', re.MULTILINE)

dom_regex = re.compile(r'''(?:\s|[\(\/<>|@'=])([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]{2,})+)(?:$|\?|\s|#|&|[\/<>'\)])''', re.MULTILINE)
ipv4_regex = re.compile(r'''((?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))''', re.MULTILINE)


# From https://gist.github.com/mnordhoff/2213179 : IPv6 with zone ID (RFC 6874)
ipv6_regex = re.compile('((?:[0-9A-Fa-f]{1,4}:){6}(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}|(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))|::(?:[0-9A-Fa-f]{1,4}:){5}(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}|(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))|(?:[0-9A-Fa-f]{1,4})?::(?:[0-9A-Fa-f]{1,4}:){4}(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}|(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))|(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4})?::(?:[0-9A-Fa-f]{1,4}:){3}(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}|(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))|(?:(?:[0-9A-Fa-f]{1,4}:){,2}[0-9A-Fa-f]{1,4})?::(?:[0-9A-Fa-f]{1,4}:){2}(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}|(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))|(?:(?:[0-9A-Fa-f]{1,4}:){,3}[0-9A-Fa-f]{1,4})?::[0-9A-Fa-f]{1,4}:(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}|(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))|(?:(?:[0-9A-Fa-f]{1,4}:){,4}[0-9A-Fa-f]{1,4})?::(?:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}|(?:(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5]))|(?:(?:[0-9A-Fa-f]{1,4}:){,5}[0-9A-Fa-f]{1,4})?::[0-9A-Fa-f]{1,4}|(?:(?:[0-9A-Fa-f]{1,4}:){,6}[0-9A-Fa-f]{1,4})?::)')

# simple version for searching for URLs
# character set based on http://tools.ietf.org/html/rfc3986
# url_regex_simple = re.compile(r'''(?i)\b((?:(hxxps?|https?|ftps?)://)[^ ]+)''', re.VERBOSE | re.MULTILINE)
url_regex_simple = re.compile(r'''(([a-z]{3,}s?:\/\/)[a-z0-9\-_:]+(\.[a-z0-9\-_]+)*''' +
                              r'''(\/[a-z0-9_\-\.~!*'();:@&=+$,\/  ?%#\[\]]*)?)''',
                              re.VERBOSE | re.MULTILINE | re.I)

priv_ip_regex = re.compile(r"^(((10(\.\d{1,3}){3})|(192\.168(\.\d{1,3}){2})|(172\.(([1][6-9])|([2]\d)|([3][0-1]))(\.\d{1,3}){2}))|(127(\.\d{1,3}){3})|(::1))")

reg_date = re.compile(r';[ \w\s:,+\-\(\)]+$')
no_par = re.compile(r'\([^()]*\)')


################################################


def get_raw_body_text(msg: email.message.Message) -> typing.List[typing.Tuple[typing.Any, typing.Any, typing.Any]]:
    """This method recursively retrieves all e-mail body parts and returns them as a list.

    Args:
        msg (email.message.Message): The actual e-mail message or sub-message.

    Returns:
        list: Returns a list of sets which are in the form of "set(encoding, raw_body_string, message field headers)"
    """
    raw_body = []  # type: typing.List[typing.Tuple[typing.Any, typing.Any,typing.Any]]

    if msg.is_multipart():
        for part in msg.get_payload():  # type: ignore
            raw_body.extend(get_raw_body_text(part))  # type: ignore
    else:
        # Treat text document attachments as belonging to the body of the mail.
        # Attachments with a file-extension of .htm/.html are implicitely treated
        # as text as well in order not to escape later checks (e.g. URL scan).

        filename = msg.get_filename('').lower()

        if ('content-disposition' not in msg and msg.get_content_maintype() == 'text') \
            or (filename.endswith('.html') or \
            filename.endswith('.htm')):
            encoding = msg.get('content-transfer-encoding', '').lower()

            charset = msg.get_content_charset()
            if not charset:
                raw_body_str = msg.get_payload(decode=True)
            else:
                try:
                    raw_body_str = msg.get_payload(decode=True).decode(charset, 'ignore')
                except Exception:
                    raw_body_str = msg.get_payload(decode=True).decode('ascii', 'ignore')

            raw_body.append((encoding, raw_body_str, msg.items()))

    return raw_body


def get_file_extension(filename: str) -> str:
    """Return the file extention of a given filename

    Args:
      filename (str): The file name.

    Returns:
      str: The lower-case file extension
    """
    extension = ''
    dot_idx = filename.rfind('.')

    if dot_idx != -1:
        extension = filename[dot_idx + 1:]

    return extension.lower()


def get_file_hash(data: bytes) -> typing.Dict[str, str]:
    """Generate hashes of various types (``MD5``, ``SHA-1``, ``SHA-256``, ``SHA-512``)
    for the provided data.

    Args:
      data (bytes): The data to calculate the hashes on.

    Returns:
      dict: Returns a dict with as key the hash-type and value the calculated hash.
    """
    hashalgo = ['md5', 'sha1', 'sha256', 'sha512']
    hash_ = {}

    for k in hashalgo:
        ha = getattr(hashlib, k)
        h = ha()
        h.update(data)
        hash_[k] = h.hexdigest()

    return hash_


def wrap_hash_sha256(string: str) -> str:
    """Generate a SHA256 hash for a given string.

    Args:
        string (str): String to calculate the hash on.

    Returns:
        str: Returns the calculated hash as a string.
    """
    _string = string.encode('utf-8')

    return hashlib.sha256(_string).hexdigest()


def traverse_multipart(msg: email.message.Message, counter: int = 0, include_attachment_data: bool = False) -> typing.Dict[str, typing.Any]:
    """Recursively traverses all e-mail message multi-part elements and returns in a parsed form as a dict.

    Args:
        msg (email.message.Message): An e-mail message object.
        counter (int, optional): A counter which is used for generating attachments
            file-names in case there are none found in the header. Default = 0.
        include_attachment_data (bool, optional): If true, method includes the raw attachment data when
            returning. Default = False.

    Returns:
        dict: Returns a dict with all original multi-part headers as well as generated hash check-sums,
            date size, file extension, real mime-type.
    """
    attachments = {}

    if magic:
        ms = magic.open(magic.NONE)
        ms.load()

    if msg.is_multipart():
        for part in msg.get_payload():  # type: ignore
            attachments.update(traverse_multipart(part, counter, include_attachment_data))  # type: ignore
    else:
        lower_keys = dict((k.lower(), v) for k, v in msg.items())

        if 'content-disposition' in lower_keys or not msg.get_content_maintype() == 'text':
            # if it's an attachment-type, pull out the filename
            # and calculate the size in bytes
            data = msg.get_payload(decode=True)  # type: bytes  # type is always bytes here
            file_size = len(data)

            filename = msg.get_filename('')
            if filename == '':
                filename = 'part-{0:03d}'.format(counter)
            else:
                filename = eml_parser.decode.decode_field(filename)

            extension = get_file_extension(filename)
            hash_ = get_file_hash(data)

            file_id = str(uuid.uuid1())
            attachments[file_id] = {}
            attachments[file_id]['filename'] = filename
            attachments[file_id]['size'] = file_size

            if extension:
                attachments[file_id]['extension'] = extension
            attachments[file_id]['hash'] = hash_

            if magic:
                attachments[file_id]['mime_type'] = ms.buffer(data)
                # attachments[file_id]['mime_type_short'] = attachments[file_id]['mime_type'].split(",")[0]
                ms = magic.open(magic.MAGIC_MIME_TYPE)
                ms.load()
                attachments[file_id]['mime_type_short'] = ms.buffer(data)

            if include_attachment_data:
                attachments[file_id]['raw'] = base64.b64encode(data)

            ch = {}  # type: typing.Dict[str, typing.List[str]]
            for k, v in msg.items():
                k = k.lower()
                if k in ch:
                    # print "%s<<<>>>%s" % (k, v)
                    ch[k].append(v)
                else:
                    ch[k] = [v]

            attachments[file_id]['content_header'] = ch

            counter += 1
    return attachments


def decode_email(eml_file: str, include_raw_body: bool = False, include_attachment_data: bool = False, pconf: typing.Optional[dict]=None) -> dict:
    """Function for decoding an EML file into an easily parsable structure.
    Some intelligence is applied while parsing the file in order to work around
    broken files.
    Besides just parsing, this function also computes hashes and extracts meta
    information from the source file.

    Args:
      eml_file (str): Full absolute path to the file to be parsed.
      include_raw_body (bool, optional): Boolean paramter which indicates whether
                                         to include the original file contents in
                                         the returned structure. Default is False.
      include_attachment_data (bool, optional): Boolean paramter which indicates whether
                                                to include raw attachment data in the
                                                returned structure. Default is False.
      pconf (dict, optional): A dict with various optinal configuration parameters,
                              e.g. whitelist IPs, whitelist e-mail addresses, etc.

    Returns:
      dict: A dictionary with the content of the EML parsed and broken down into
            key-value pairs.
    """
    with open(eml_file, 'rb') as fp:
        msg = email.message_from_binary_file(fp, policy=email.policy.default)

    return parse_email(msg, include_raw_body, include_attachment_data, pconf)


def decode_email_s(eml_file: str, include_raw_body: bool = False, include_attachment_data: bool = False, pconf: typing.Optional[dict]=None) -> dict:
    """Function for decoding an EML file into an easily parsable structure.
    Some intelligence is applied while parsing the file in order to work around
    broken files.
    Besides just parsing, this function also computes hashes and extracts meta
    information from the source file.

    Args:
        eml_file (str): Contents of the raw EML file passed to this function as string.
        include_raw_body (bool, optional): Boolean paramter which indicates whether
                                           to include the original file contents in
                                           the returned structure. Default is False.
        include_attachment_data (bool, optional): Boolean paramter which indicates whether
                                                  to include raw attachment data in the
                                                  returned structure. Default is False.
        pconf (dict, optional): A dict with various optinal configuration parameters,
                                e.g. whitelist IPs, whitelist e-mail addresses, etc.

    Returns:
        dict: A dictionary with the content of the EML parsed and broken down into
              key-value pairs.
    """
    msg = email.message_from_string(eml_file, policy=email.policy.default)
    return parse_email(msg, include_raw_body, include_attachment_data, pconf)


def decode_email_b(eml_file: bytes, include_raw_body: bool = False, include_attachment_data: bool = False, pconf: typing.Optional[dict]=None) -> dict:
    """Function for decoding an EML file into an easily parsable structure.
    Some intelligence is applied while parsing the file in order to work around
    broken files.
    Besides just parsing, this function also computes hashes and extracts meta
    information from the source file.

    Args:
        eml_file (bytes): Contents of the raw EML file passed to this function as string.
        include_raw_body (bool, optional): Boolean paramter which indicates whether
                                           to include the original file contents in
                                           the returned structure. Default is False.
        include_attachment_data (bool, optional): Boolean paramter which indicates whether
                                                  to include raw attachment data in the
                                                  returned structure. Default is False.
        pconf (dict, optional): A dict with various optinal configuration parameters,
                                e.g. whitelist IPs, whitelist e-mail addresses, etc.

    Returns:
        dict: A dictionary with the content of the EML parsed and broken down into
              key-value pairs.
    """
    msg = email.message_from_bytes(eml_file, policy=email.policy.default)
    return parse_email(msg, include_raw_body, include_attachment_data, pconf)


def get_uri_ondata(body: str) -> typing.List[str]:
    """Function for extracting URLs from the input string.

    Args:
        body (str): Text input which should be searched for URLs.

    Returns:
        list: Returns a list of URLs found in the input string.
    """
    list_observed_urls = []  # type: typing.List[str]

    for match in url_regex_simple.findall(body):
        found_url = match[0].replace('hxxp', 'http')
        found_url = urllib.parse.urlparse(found_url).geturl()
        # let's try to be smart by stripping of noisy bogus parts
        found_url = re.split(r'''[\', ", \,, \), \}, \\]''', found_url)[0]
        list_observed_urls.append(found_url)

    return list_observed_urls


# Convert email to a list from a given header field.
def headeremail2list(mail: email.message.Message, header: str) -> typing.List[str]:
    """Parses a given header field with e-mail addresses to a list of e-mail addresses.

    Args:
        mail (email.message.Message): An e-mail message object.
        header (str): The header field to decode.

    Returns:
        list: Returns a list of strings which represent e-mail addresses.
    """
    field = email.utils.getaddresses(mail.get_all(header, []))
    return_field = []
    for m in field:
        if not m[1] == '':
            return_field.append(m[1].lower())
    return return_field


# Iterator that give all position of a given pattern (no regex)
# FIXME :
# Error may occurs when using unicode-literals or python 3 on dirty emails
# Need to check if buffer is a clean one
# may be tested with this byte code:
# -> 00000b70  61 6c 20 32 39 b0 20 6c  75 67 6c 69 6f 20 32 30  |al 29. luglio 20|
# Should crash on "B0".
def findall(pat: str, data: str) -> typing.Iterator[int]:
    """Iterator that give all position of a given pattern (no regex).

    Args:
        pat (str): Pattern to seek
        data (str): buffer

    Yields:
        int: Yields the next position
    """
    i = data.find(pat)
    while i != -1:
        yield i
        i = data.find(pat, i + 1)


def noparenthesis(line: str) -> str:
    """Remove nested parenthesis, until none are present.

    Args:
        line (str): Input text to search in for parenthesis.


    Returns:
        str: Return a string with all paranthesis removed.
    """
    idem = False
    line_ = line

    while not idem:
        lline = line_
        line_ = re.sub(no_par, '', line_)
        if lline == line_:
            idem = True

    return line_


def getkey(item: typing.List[typing.Any]) -> typing.Any:
    """Returns the first element of a list.

    Args:
        item (list): List.

    Returns:
        object: Returns the first item of any kind of list object.
    """
    return item[0]


def regprep(line: str) -> str:
    for ch in '^$[]()+?.':
        line = re.sub("\\" + ch, '\\\\' + ch, line)
    return line


def cleanline(line: str) -> str:
    """Remove space and ; from start/end of line until it is not possible.

    Args:
        line (str): Line to clean.

    Returns:
        str: Cleaned string.
    """
    idem = False
    while not idem:
        lline = line
        line = line.strip(";")
        line = line.strip(" ")
        if lline == line:
            idem = True
    return line


def robust_string2date(line: str) -> datetime.datetime:
    """Parses a date string to a datetime.datetime object using different methods.
    It is guaranteed to always return a valid datetime.datetime object.
    If first tries the built-in email module method for parsing the date according
    to related RFC's.
    If this fails it returns a datetime.datetime object representing
    "1970-01-01 00:00:00 +0000".
    In case there is no timezone information in the parsed date, we set it to UTC.

    Args:
        line (str): A string which should be parsed.

    Returns:
        datetime.datetime: Returns a datetime.datetime object.  
    """
    # "." -> ":" replacement is for fixing bad clients (e.g. outlook express)
    default_date = '1970-01-01 00:00:00 +0000'
    msg_date = line.replace('.', ':')
    date_ = email.utils.parsedate_to_datetime(msg_date)

    if date_ is None:
        # Now we are facing an invalid date.
        return dateutil.parser.parse(default_date)
    elif date_.tzname() is None:
        return date_.replace(tzinfo=datetime.timezone.utc)
    else:
        return date_


def parserouting(line: str) -> typing.Dict[str, typing.Any]:
    """This method tries to parsed a e-mail header received line
    and extract machine readable information.
    Note that there are a large number of formats for these lines
    and a lot of weird ones which are not commonly used.
    We try our best to match a large number of formats.

    Args:
        line (str): Received line to be parsed.

    Returns:
        dict: Returns a dict with the extracted information.
    """
    #    if re.findall(reg_date, line):
    #        return 'date\n'
    # Preprocess the line to simplify from/by/with/for border detection.
    out = {}  # type: typing.Dict[str, typing.Any]  # Result
    out['src'] = line
    line = line.lower()  # Convert everything to lowercase
    npline = re.sub(r'\)', ' ) ', line)  # nORMALISE sPACE # Re-space () ")by " exists often
    npline = re.sub(r'\(', ' ( ', npline)  # nORMALISE sPACE # Re-space ()
    npline = re.sub(';', ' ; ', npline)  # nORMALISE sPACE # Re-space ;
    npline = noparenthesis(npline)  # Remove any "()"
    npline = re.sub('  *', ' ', npline)  # nORMALISE sPACE
    npline = npline.strip('\n')  # Remove any NL
    raw_find_data = re.findall(reg_date, npline)  # extract date on end line.

    # Detect "sticked lines"
    if " received: " in npline:
        out['warning'] = ['Merged Received headers']
        return out

    if raw_find_data:
        npdate = raw_find_data[0]  # Remove spaces and starting ;
        npdate = npdate.lstrip(";")  # Remove Spaces and stating ; from date
        npdate = npdate.strip()
    else:
        npdate = ""

    npline = npline.replace(npdate, "")  # Remove date from input line
    npline = npline.strip(' ')  # Remove any border WhiteSpace

    borders = ['from ', 'by ', 'with ', 'for ']
    candidate = []  # type: typing.List[str]
    result = []  # type: typing.List[typing.Dict[str, typing.Any]]

    # Scan the line to determine the order, and presence of each "from/by/with/for" words
    for word in borders:
        candidate = list(borders)
        candidate.remove(word)
        for endword in candidate:
            if word in npline:
                loc = npline.find(word)
                end = npline.find(endword)
                if end < loc or end == -1:
                    end = 0xfffffff   # Kindof MAX 31 bits
                result.append({'name_in': word, 'pos': loc, 'name_out': endword, 'weight': end + loc})
                # print {'name_in': word, 'pos': loc, 'name_out': endword, 'weight': end+loc}

    # Create the word list... "from/by/with/for" by sorting the list.
    if not result:
        out['warning'] = ['Nothing Parsable']
        return out

    tout = []
    for word in borders:
        result_max = 0xffffffff
        line_max = {}  # type: typing.Dict[str, typing.Any]
        for eline in result:
            if eline['name_in'] == word and eline['weight'] <= result_max:
                result_max = eline['weight']
                line_max = eline

        if len(line_max) > 0:
            tout.append([line_max.get('pos'), line_max.get('name_in')])

    tout = sorted(tout, key=getkey)

    # build regex.
    reg = ""
    for item in tout:
        reg += item[1] + "(?P<" + item[1].strip() + ">.*)"  # type: ignore
    if npdate:
        reg += regprep(npdate)

    reparse = re.compile(reg)
    reparseg = reparse.search(line)

    # Fill the data
    for item in borders:  # type: ignore
        try:
            out[item.strip()] = cleanline(reparseg.group(item.strip()))  # type: ignore
        except Exception:
            pass
    out['date'] = robust_string2date(npdate)

    # Fixup for "From" in "for" field
    # ie google, do that...
    if out.get('for'):
        if 'from' in out.get('for', ''):
            temp = re.split(' from ', out['for'])
            out['for'] = temp[0]
            out['from'] = '{0} {1}'.format(out['from'], " ".join(temp[1:]))

        m = email_regex.findall(out['for'])
        if m:
            out['for'] = list(set(m))
        else:
            del out['for']

    # Now.. find IP and Host in from
    if out.get('from'):
        out['from'] = give_dom_ip(out['from'])
        if not out.get('from', []):  # if array is empty remove
            del out['from']

    # Now.. find IP and Host in from
    if out.get('by'):
        out['by'] = give_dom_ip(out['by'])
        if not out.get('by', []):  # If array is empty remove
            del out['by']

    return out


def give_dom_ip(line: str) -> typing.List[str]:
    """Method returns all domains, IPv4 and IPv6 addresses found in a given string.

    Args:
        line (str): String to search in.

    Returns:
        list: Unique list of strings with matches
    """
    m = dom_regex.findall(" " + line) + ipv4_regex.findall(line) + ipv6_regex.findall(line)

    return list(set(m))


def parse_email(msg: email.message.Message, include_raw_body: bool = False, include_attachment_data: bool = False, pconf: typing.Optional[dict]=None) -> dict:
    """Parse an e-mail and return a dictionary containing the various parts of
    the e-mail broken down into key-value pairs.

    Args:
      msg (str): Raw EML e-mail string.
      include_raw_body (bool, optional): If True, includes the raw body in the resulting
                               dictionary. Defaults to False.
      include_attachment_data (bool, optional): If True, includes the full attachment
                                                data in the resulting dictionary.
                                                Defaults to False.
      pconf (dict, optional): A dict with various optinal configuration parameters,
                              e.g. whitelist IPs, whitelist e-mail addresses, etc.

    Returns:
      dict: A dictionary with the content of the EML parsed and broken down into
            key-value pairs.
    """
    header = {}  # type: typing.Dict[str, typing.Any]
    report_struc = {}  # type: typing.Dict[str, typing.Any]  # Final structure
    headers_struc = {}  # type: typing.Dict[str, typing.Any]  # header_structure
    bodys_struc = {}  # type: typing.Dict[str, typing.Any]  # body structure

    # If no pconf was specified, default to empty dict
    pconf = pconf or {}

    # If no whitelisting of if is required initiate the empty variable arry
    if 'whiteip' not in pconf:
        pconf['whiteip'] = []
    # If no whitelisting of if is required initiate the empty variable arry
    if 'whitefor' not in pconf:
        pconf['whitefor'] = []

    # parse and decode subject
    subject = msg.get('subject', '')
    headers_struc['subject'] = eml_parser.decode.decode_field(subject)

    # If parsing had problem... report it...
    if msg.defects:
        headers_struc['defect'] = []
        for exception in msg.defects:
            headers_struc['defect'].append(str(exception))

    # parse and decode from
    # @TODO verify if this hack is necessary for other e-mail fields as well
    msg_header_field = str(msg.get('from', '')).lower()

    m = email_regex.search(msg_header_field)
    if m:
        headers_struc['from'] = m.group(1)
    else:
        from_ = email.utils.parseaddr(msg.get('from', '').lower())
        headers_struc['from'] = from_[1]

    # parse and decode to
    headers_struc['to'] = headeremail2list(msg, 'to')
    # parse and decode Cc
    headers_struc['cc'] = headeremail2list(msg, 'cc')
    if not headers_struc['cc']:
        headers_struc.pop('cc')

    # parse and decode delivered-to
    headers_struc['delivered_to'] = headeremail2list(msg, 'delivered-to')
    if not headers_struc['delivered_to']:
        headers_struc.pop('delivered_to')

    # parse and decode Date
    # If date field is present
    if 'date' in msg:
        headers_struc['date'] = robust_string2date(msg.get('date'))
    else:
        # If date field is absent...
        headers_struc['date'] = dateutil.parser.parse('1970-01-01T00:00:00+0000')

    # mail receiver path / parse any domain, e-mail
    # @TODO parse case where domain is specified but in parantheses only an IP
    headers_struc['received'] = []
    headers_struc['received_email'] = []
    headers_struc['received_domain'] = []
    headers_struc['received_ip'] = []
    try:
        found_smtpin = collections.Counter()  # type: collections.Counter  # Array for storing potential duplicate "HOP"

        for l in msg.get_all('received', []):
            l = str(l)

            l = re.sub(r'(\r|\n|\s|\t)+', ' ', l.lower(), flags=re.UNICODE)

            # Parse and split routing headers.
            # Return dict of array
            #   date string
            #   from array
            #   for array
            #   by array
            #   with string
            #   warning array
            current_line = parserouting(l)

            # If required collect the IP of the gateway that have injected the mail.
            # Iterate all parsed item and find IP
            # It is parsed from the MOST recent to the OLDEST (from IN > Out)
            # We match external IP from the most "OUT" Found.
            # Warning .. It may be spoofed !!
            # It add a warning if multiple identical items are found.

            if 'byhostentry' in pconf:
                if current_line.get('by'):
                    for by_item in current_line.get('by'):  # type: ignore
                        for byhostentry in pconf['byhostentry']:
                            # print ("%s %s" % (byhostentry, by_item))
                            if byhostentry.lower() in by_item:
                                # Save the last Found.. ( most external )
                                headers_struc['received_src'] = current_line.get('from')

                                # Increment watched by detection counter, and warn if needed
                                found_smtpin[byhostentry.lower()] += 1
                                if found_smtpin[byhostentry.lower()] > 1:  # Twice found the header...
                                    if current_line.get('warning'):
                                        current_line['warning'].append(['Duplicate SMTP by entrypoint'])
                                    else:
                                        current_line['warning'] = ['Duplicate SMTP by entrypoint']

            headers_struc['received'].append(current_line)

            # Parse IP in "received headers"
            for ips in ipv6_regex.findall(l):
                if not priv_ip_regex.match(ips):
                    if ips.lower() not in pconf['whiteip']:
                        headers_struc['received_ip'].append(ips.lower())
            for ips in ipv4_regex.findall(l):
                if not priv_ip_regex.match(ips):
                    if ips not in pconf['whiteip']:
                        headers_struc['received_ip'].append(ips.lower())

            # search for domain / e-mail addresses
            for m in recv_dom_regex.findall(l):
                checks = True
                if '.' in m:  # type: ignore  # type of findall is list[str], so this is correct
                    try:
                        if ipv4_regex.match(m) or m == '127.0.0.1':  # type: ignore  # type of findall is list[str], so this is correct
                            checks = False
                    except ValueError:
                        pass
                if checks:
                    headers_struc['received_domain'].append(m)

            # Extracts emails, but not the ones in the FOR on this received headers line.
            # Process Here line per line not finally to not miss a email not in from
            m = email_regex.findall(l)  # type: ignore
            if m:
                for mail_candidate in m:  # type: ignore  # type of findall is list[str], so this is correct
                    if current_line.get('for'):
                        if mail_candidate not in current_line.get('for'):  # type: ignore
                            headers_struc['received_email'] += [mail_candidate]
                    else:
                        headers_struc['received_email'] += [mail_candidate]

    except TypeError:  # Ready to parse email without received headers.
        pass

    # Concatenate for emails into one array | uniq
    # for rapid "find"
    if headers_struc.get('received'):
        headers_struc['received_foremail'] = []
        for line in headers_struc['received']:
            if line.get('for'):
                for itemfor in line.get('for'):
                    if itemfor not in pconf['whitefor']:
                        headers_struc['received_foremail'] += line.get('for')

    # Uniq data found
    headers_struc['received_email'] = list(set(headers_struc['received_email']))
    headers_struc['received_domain'] = list(set(headers_struc['received_domain']))
    headers_struc['received_ip'] = list(set(headers_struc['received_ip']))

    # Clean up if empty
    if not headers_struc['received_email']:
        headers_struc.pop('received_email')
    if 'received_foremail' in headers_struc:
        if not headers_struc['received_foremail']:
            del headers_struc['received_foremail']
        else:
            headers_struc['received_foremail'] = list(set(headers_struc['received_foremail']))
    if not headers_struc['received_domain']:
        del headers_struc['received_domain']
    if not headers_struc['received_ip']:
        del headers_struc['received_ip']

    # Parse text body
    raw_body = get_raw_body_text(msg)

    if include_raw_body:
        bodys_struc['raw_body'] = raw_body

    bodys = {}
    multipart = True  # Is it a multipart email ?
    if len(raw_body) == 1:
        multipart = False  # No only "one" Part
    for body_tup in raw_body:
        bodie = {}  # type: typing.Dict[str, typing.Any]
        encoding, body, body_multhead = body_tup
        # Parse any URLs and mail found in the body
        list_observed_urls = []  # type: typing.List[str]
        list_observed_email = []  # type: typing.List[str]
        list_observed_dom = []  # type: typing.List[str]
        list_observed_ip = []  # type: typing.List[str]

        if sys.version_info >= (3, 0) and isinstance(body, (bytearray, bytes)):
            body = body.decode('utf-8', 'ignore')

        # If we start directly a findall on 500K+ body we got time and memory issues...
        # if more than 4K.. lets cheat, we will cut around the thing we search "://, @, ."
        # in order to reduce regex complexity.
        if len(body) < 4096:
            list_observed_urls = get_uri_ondata(body)
            for match in email_regex.findall(body):
                list_observed_email.append(match.lower())
            for match in dom_regex.findall(body):
                list_observed_dom.append(match.lower())
            for match in ipv4_regex.findall(body):
                if not priv_ip_regex.match(match):
                    if match not in pconf['whiteip']:
                        list_observed_ip.append(match)
            for match in ipv6_regex.findall(body):
                if not priv_ip_regex.match(match):
                    if match.lower() not in pconf['whiteip']:
                        list_observed_ip.append(match.lower())
        else:
            for scn_pt in findall('://', body):
                list_observed_urls = get_uri_ondata(body[scn_pt - 16:scn_pt + 4096]) + list_observed_urls

            for scn_pt in findall('@', body):
                # RFC 3696, 5322, 5321 for email size limitations
                for match in email_regex.findall(body[scn_pt - 64:scn_pt + 255]):
                    list_observed_email.append(match.lower())

            for scn_pt in findall('.', body):
                # The maximum length of a fqdn, not a hostname, is 1004 characters RFC1035
                # The maximum length of a hostname is 253 characters. Imputed from RFC952, RFC1123 and RFC1035.
                for match in dom_regex.findall(body[scn_pt - 253:scn_pt + 1004]):
                    list_observed_dom.append(match.lower())

                # Find IPv4 addresses
                for match in ipv4_regex.findall(body[scn_pt - 11:scn_pt + 3]):
                    if not priv_ip_regex.match(match):
                        if match not in pconf['whiteip']:
                            list_observed_ip.append(match)

            for scn_pt in findall(':', body):
                # The maximum length of IPv6 is 32 Char + 7 ":"
                for match in ipv6_regex.findall(body[scn_pt - 4:scn_pt + 35]):
                    if not priv_ip_regex.match(match):
                        if match.lower() not in pconf['whiteip']:
                            list_observed_ip.append(match.lower())

        # Report uri,email and observed domain or hash if no raw body
        if include_raw_body:
            if list_observed_urls:
                bodie['uri'] = list(set(list_observed_urls))

            if list_observed_email:
                bodie['email'] = list(set(list_observed_email))

            if list_observed_dom:
                bodie['domain'] = list(set(list_observed_dom))

            if list_observed_ip:
                bodie['ip'] = list(set(list_observed_ip))

        else:
            if list_observed_urls:
                bodie['uri_hash'] = []
                for uri in list(set(list_observed_urls)):
                    bodie['uri_hash'].append(wrap_hash_sha256(uri.lower()))
            if list_observed_email:
                bodie['email_hash'] = []
                for emel in list(set(list_observed_email)):
                    # Email already lowered
                    bodie['email_hash'].append(wrap_hash_sha256(emel))
            if list_observed_dom:
                bodie['domain_hash'] = []
                for uri in list(set(list_observed_dom)):
                    bodie['domain_hash'].append(wrap_hash_sha256(uri.lower()))
            if list_observed_ip:
                bodie['ip_hash'] = []
                for fip in list(set(list_observed_ip)):
                    # IP (v6) already lowered
                    bodie['ip_hash'].append(wrap_hash_sha256(fip))

        # For mail without multipart we will only get the "content....something" headers
        # all other headers are in "header"
        # but we need to convert header tuples in dict..
        # "a","toto"           a: [toto,titi]
        # "a","titi"   --->    c: [truc]
        # "c","truc"
        ch = {}  # type: typing.Dict[str, typing.List]
        for k, v in body_multhead:
            # We are using replace . to : for avoiding issue in mongo
            k = k.lower().replace('.', ':')  # Lot of lowers, precompute :) .
            # print v
            if multipart:
                if k in ch:
                    ch[k].append(v)
                else:
                    ch[k] = [v]
            else:  # if not multipart, store only content-xx related header with part
                if k.startswith('content'):  # otherwise, we got all header headers
                    k = k.lower().replace('.', ':')
                    if k in ch:
                        ch[k].append(v)
                    else:
                        ch[k] = [v]
        bodie['content_header'] = ch  # Store content headers dict

        if include_raw_body:
            bodie['content'] = body

        # Sometimes dirty peoples plays with multiple header.
        # We "display" the "LAST" one .. as do a thunderbird
        val = ch.get('content-type')
        if val:
            header_val = str(val[-1])
            bodie['content_type'] = header_val.split(';', 1)[0].strip()

        # Try hashing.. with failback for incorrect encoding (non ascii)
        try:
            bodie['hash'] = hashlib.sha256(body).hexdigest()
        except Exception:
            bodie['hash'] = hashlib.sha256(body.encode('UTF-8')).hexdigest()

        uid = str(uuid.uuid1())
        bodys[uid] = bodie

    bodys_struc = bodys

    # Get all other bulk raw headers
    # "a","toto"           a: [toto,titi]
    # "a","titi"   --->    c: [truc]
    # "c","truc"
    #
    for k, v in msg.items():
        # We are using replace . to : for avoiding issue in mongo
        k = k.lower().replace('.', ':')  # Lot of lower, precompute...
        value = str(v)

        if k in header:
            header[k].append(value)
        else:
            header[k] = [value]

    headers_struc['header'] = header

    # parse attachments
    report_struc['attachment'] = traverse_multipart(msg, 0, include_attachment_data)

    # Dirty hack... transphorm hash in list.. need to be done in the function.
    # Mandatory to search efficiently in mongodb
    # See Bug 11 of eml_parser
    if not report_struc['attachment']:
        del report_struc['attachment']
    else:
        newattach = []
        for attachment in report_struc['attachment']:
            newattach.append(report_struc['attachment'][attachment])
        report_struc['attachment'] = newattach

    newbody = []
    for body in bodys_struc:
        newbody.append(bodys_struc[body])
    report_struc['body'] = newbody
    # End of dirty hack

    # Get all other bulk headers
    report_struc['header'] = headers_struc

    return report_struc
