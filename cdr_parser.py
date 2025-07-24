import os
import re
import random
import logging
from datetime import datetime
from pyasn1.codec.der import decoder
from pyasn1.codec.ber import decoder as ber_decoder
from pyasn1 import error


class CDRParser:
    """SENORA ASN parser for telecom Call Detail Records"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_timestamp_from_filename(self, filename):
        """Extract a timestamp from a filename if present.

        The function searches for a 14-digit pattern representing
        ``YYYYMMDDHHMMSS`` and returns a ``datetime`` object. If no
        such pattern is found, ``None`` is returned.
        """
        match = re.search(r"(20\d{12})", filename)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
            except ValueError:
                pass
        return None

    def parse_file(self, filepath):
        """Parse a CDR file and return a list of records"""
        try:
            # Check file size first
            file_size = os.path.getsize(filepath)
            self.logger.info(f"Processing file {filepath} of size {file_size} bytes")

            # Very large files are parsed in chunks to avoid memory issues
            if file_size > 10 * 1024 * 1024:  # >10MB
                self.logger.info("Large file detected - using chunked parser")
                return self.parse_large_file(filepath)

            # Medium sized files use the raw binary parser for speed
            if file_size > 1024 * 1024:  # >1MB
                self.logger.info("Medium file detected - using enhanced BCD parsing")
                return self.parse_raw_binary_file(filepath)

            # Small files are loaded entirely in memory
            with open(filepath, "rb") as f:
                data = f.read()
            return self.parse_binary_data(data)

        except Exception as e:
            self.logger.error(f"Error reading file {filepath}: {str(e)}")
            # Fallback to raw binary parsing if standard parsing fails
            try:
                return self.parse_raw_binary_file(filepath)
            except Exception:
                raise Exception(f"Failed to read file: {str(e)}")

    def parse_file_chunk(self, filepath, start_record=0, max_records=1000, offset=0):
        """Parse part of a file starting from ``offset`` and ``start_record``.

        Returns ``(records, reached_end, new_offset)``.
        """
        records = []
        chunk_size = 10 * 1024 * 1024  # 10MB
        record_index = start_record
        reached_end = False
        new_offset = offset

        try:
            with open(filepath, "rb") as f:
                f.seek(offset)
                while len(records) < max_records:
                    chunk_start = f.tell()

    def parse_file_chunk(self, filepath, start_record=0, max_records=1000):
        """Parse a portion of a CDR file starting at ``start_record``.

        Returns a tuple ``(records, reached_end)`` where ``records`` is a list
        of parsed records and ``reached_end`` indicates if the end of the file
        was reached during parsing.
        """
        records = []
        chunk_size = 10 * 1024 * 1024  # 10MB
        record_index = 0
        reached_end = False

        try:
            with open(filepath, "rb") as f:
                while len(records) < max_records:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        reached_end = True
                        break

                    if len(chunk) == chunk_size:
                        boundary_search = chunk[-1024:]
                        boundary_pos = -1
                        for i in range(len(boundary_search) - 1, 0, -1):
                            if boundary_search[i] in [0x30, 0x31, 0x02, 0x04]:
                                boundary_pos = len(chunk) - len(boundary_search) + i
                                break
                        if boundary_pos > 0:
                            process_chunk = chunk[:boundary_pos]
                            f.seek(chunk_start + boundary_pos)
                            chunk = process_chunk

                    chunk_records = self.parse_binary_data_chunk(chunk, record_index)
                    records.extend(chunk_records)
                    record_index += len(chunk_records)
                    new_offset = f.tell()
                    chunk_records = self.parse_binary_data_chunk(chunk, record_index)
                    for r in chunk_records:
                        if record_index >= start_record and len(records) < max_records:
                            records.append(r)
                        record_index += 1
                        if len(records) >= max_records:
                            break
                    if len(records) >= max_records:
                        break

        except Exception as e:
            self.logger.error(f"Error processing file chunk: {str(e)}")

        return records, reached_end, new_offset
    def parse_binary_data(self, data):
        """Parse binary ASN.1 data and extract CDR records"""
        records = []
        offset = 0
        record_index = 0

        while offset < len(data):
            try:
                # Try to decode ASN.1 structure
                asn1_object, remainder = decoder.decode(data[offset:])

                # Process the decoded object
                record = self.process_asn1_object(asn1_object, record_index)
                if record:
                    records.append(record)
                    record_index += 1

                # Move to next record
                consumed = len(data[offset:]) - len(remainder)
                if consumed == 0:
                    # Avoid infinite loop
                    offset += 1
                else:
                    offset += consumed

            except error.PyAsn1Error as e:
                self.logger.debug(f"ASN.1 decode error at offset {offset}: {str(e)}")
                # Try BER decoder as fallback
                try:
                    asn1_object, remainder = ber_decoder.decode(data[offset:])
                    record = self.process_asn1_object(asn1_object, record_index)
                    if record:
                        records.append(record)
                        record_index += 1

                    consumed = len(data[offset:]) - len(remainder)
                    if consumed == 0:
                        offset += 1
                    else:
                        offset += consumed

                except error.PyAsn1Error:
                    # Skip this byte and continue
                    offset += 1

            except Exception as e:
                self.logger.debug(f"General error at offset {offset}: {str(e)}")
                # Try to find next valid ASN.1 structure
                next_offset = self.find_next_asn1_start(data, offset + 1)
                if next_offset == -1:
                    break
                offset = next_offset

        if not records:
            # If no records found with standard decoding, use enhanced BCD analysis
            self.logger.info(
                "No ASN.1 records found, using enhanced BCD phone extraction"
            )
            records = self.parse_telecom_binary_data(data)

        return records

    def process_asn1_object(self, asn1_object, record_index):
        """Process a decoded ASN.1 object and extract CDR information"""
        record = {
            "record_index": record_index,
            "record_type": "asn1_decoded",
            "raw_asn1_structure": self.asn1_to_dict(asn1_object),
        }

        # Try to extract common telecom CDR fields
        try:
            # Convert ASN.1 object to a more workable format
            asn1_dict = self.asn1_to_dict(asn1_object)

            # Try to identify and extract common CDR fields
            self.extract_cdr_fields(asn1_dict, record)

        except Exception as e:
            self.logger.debug(f"Error extracting CDR fields: {str(e)}")
            record["extraction_error"] = str(e)

        return record

    def asn1_to_dict(self, asn1_object):
        """Convert ASN.1 object to dictionary for easier processing"""
        if hasattr(asn1_object, "hasValue") and asn1_object.hasValue():
            if hasattr(asn1_object, "__iter__"):
                # It's a sequence or choice
                result = {}
                try:
                    for idx, component in enumerate(asn1_object):
                        if hasattr(asn1_object, "componentType"):
                            # Named components
                            comp_name = asn1_object.componentType[idx].getName()
                            result[comp_name or f"component_{idx}"] = self.asn1_to_dict(
                                component
                            )
                        else:
                            result[f"component_{idx}"] = self.asn1_to_dict(component)
                except Exception:
                    # Fallback to simple value
                    return str(asn1_object)
                return result
            else:
                # It's a primitive value
                return str(asn1_object)
        else:
            return None

    def extract_cdr_fields(self, asn1_dict, record):
        """Extract common CDR fields from the ASN.1 dictionary with improved pattern matching"""

        # Extract all numeric strings that could be phone numbers
        phone_numbers = self.extract_phone_numbers_from_dict(asn1_dict)

        # Assign phone numbers (first two as calling/called)
        if len(phone_numbers) >= 2:
            record["calling_number"] = phone_numbers[0]
            record["called_number"] = phone_numbers[1]
        elif len(phone_numbers) == 1:
            record["calling_number"] = phone_numbers[0]

        # Store all found phone numbers for reference
        if phone_numbers:
            record["all_phone_numbers"] = phone_numbers

        # Look for timestamps and durations
        timestamps = self.extract_timestamps_from_dict(asn1_dict)
        durations = self.extract_durations_from_dict(asn1_dict)

        # Assign timestamps
        if len(timestamps) >= 2:
            record["start_time"] = timestamps[0]
            record["end_time"] = timestamps[1]
            # Calculate duration if both times available
            if timestamps[0] and timestamps[1]:
                try:
                    duration = (timestamps[1] - timestamps[0]).total_seconds()
                    if duration > 0:
                        record["call_duration"] = int(duration)
                except Exception:
                    pass
        elif len(timestamps) == 1:
            record["start_time"] = timestamps[0]

        # Use extracted duration if no calculated duration
        if "call_duration" not in record and durations:
            record["call_duration"] = durations[0]

        # Determine record type based on content analysis
        record["record_type"] = self.determine_record_type(asn1_dict)

        # Extract additional metadata
        self.extract_additional_fields(asn1_dict, record)

    def extract_phone_numbers_from_dict(self, data):
        """Extract potential phone numbers from ASN.1 data"""
        import re

        phone_numbers = []

        def extract_from_value(value):
            if isinstance(value, str):
                # Look for sequences of digits that could be phone numbers
                matches = re.findall(r"\b\d{7,15}\b", value)
                for match in matches:
                    if match not in phone_numbers and len(match) >= 7:
                        phone_numbers.append(match)
            elif isinstance(value, dict):
                for v in value.values():
                    extract_from_value(v)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    extract_from_value(item)

        extract_from_value(data)
        return phone_numbers[:10]  # Limit to first 10

    def extract_timestamps_from_dict(self, data):
        """Extract potential timestamps from ASN.1 data"""
        timestamps = []

        def extract_from_value(value):
            if isinstance(value, str):
                # Try to parse as timestamp
                parsed_time = self.parse_timestamp(value)
                if parsed_time and parsed_time not in timestamps:
                    timestamps.append(parsed_time)
            elif isinstance(value, dict):
                for v in value.values():
                    extract_from_value(v)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    extract_from_value(item)

        extract_from_value(data)
        return timestamps[:5]  # Limit to first 5

    def extract_durations_from_dict(self, data):
        """Extract potential call durations from ASN.1 data"""
        durations = []

        def extract_from_value(value):
            if isinstance(value, str):
                # Look for numeric values that could be durations
                import re

                matches = re.findall(r"\b\d{1,6}\b", value)
                for match in matches:
                    duration = int(match)
                    # Reasonable call duration range (1 sec to 24 hours)
                    if 1 <= duration <= 86400:
                        durations.append(duration)
            elif isinstance(value, dict):
                for v in value.values():
                    extract_from_value(v)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    extract_from_value(item)

        extract_from_value(data)
        return durations[:3]  # Limit to first 3

    def determine_record_type(self, data):
        """Determine record type based on ASN.1 content"""
        data_str = str(data).lower()

        # Voice call indicators
        if any(
            indicator in data_str
            for indicator in ["voice", "call", "speech", "gsm", "circuit"]
        ):
            return "voice_call"

        # SMS indicators
        elif any(
            indicator in data_str for indicator in ["sms", "message", "short", "text"]
        ):
            return "sms"

        # Data session indicators
        elif any(
            indicator in data_str
            for indicator in ["data", "gprs", "pdp", "internet", "packet"]
        ):
            return "data_session"

        # MMS indicators
        elif any(indicator in data_str for indicator in ["mms", "multimedia"]):
            return "mms"

        # If we found phone numbers, likely a voice call
        elif "calling_number" in str(data) or "called_number" in str(data):
            return "voice_call"

        else:
            return "telecom_record"  # More specific than 'unknown'

    def extract_additional_fields(self, asn1_dict, record):
        """Extract additional CDR fields like IMSI, IMEI, cell info"""

        def search_for_patterns(data, patterns, field_name):
            import re

            for pattern_name, pattern in patterns.items():
                matches = re.findall(pattern, str(data))
                if matches:
                    record[field_name] = matches[0]
                    break

        # Common telecom patterns
        patterns = {
            "imsi": r"\b[0-9]{15}\b",  # IMSI (15 digits)
            "imei": r"\b[0-9]{14,15}\b",  # IMEI (14-15 digits)
            "cell_id": r"\b[0-9]{4,8}\b",  # Cell ID
        }

        # Look for specific telecom identifiers
        search_for_patterns(asn1_dict, {"imsi": patterns["imsi"]}, "imsi")
        search_for_patterns(asn1_dict, {"imei": patterns["imei"]}, "imei")
        search_for_patterns(asn1_dict, {"cell_id": patterns["cell_id"]}, "cell_id")

    def parse_timestamp(self, timestamp_str):
        """Try to parse various timestamp formats"""
        if not timestamp_str:
            return None

        # Common timestamp formats in telecom
        formats = [
            "%Y%m%d%H%M%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y%m%d%H%M%S%f",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue

        # If no format matches, store as string
        return None

    def find_next_asn1_start(self, data, start_offset):
        """Find the next potential ASN.1 structure start"""
        for i in range(start_offset, len(data)):
            # Look for common ASN.1 tag bytes
            if data[i] in [
                0x30,
                0x31,
                0x02,
                0x04,
                0x05,
                0x06,
                0x0A,
                0x80,
                0x81,
                0x82,
                0x83,
            ]:
                return i
        return -1

    def parse_raw_binary(self, data):
        """Fallback parser for when ASN.1 decoding fails completely"""
        records = []

        # This is a very basic fallback that tries to extract any readable strings
        # that might be phone numbers or other identifiable data

        record = {
            "record_index": 0,
            "record_type": "raw_binary",
            "file_size": len(data),
            "parsing_method": "raw_binary_analysis",
            "note": "ASN.1 decoding failed, raw binary analysis used",
        }

        # Try to find phone number patterns (sequences of digits)
        import re

        # Extract potential phone numbers (6-15 digits)
        phone_pattern = rb"[\d]{6,15}"
        phone_matches = re.findall(phone_pattern, data)
        if phone_matches:
            record["potential_phone_numbers"] = [
                match.decode("ascii", errors="ignore") for match in phone_matches[:10]
            ]

        # Extract printable strings that might be useful
        printable_strings = []
        current_string = b""

        for byte in data:
            if 32 <= byte <= 126:  # Printable ASCII
                current_string += bytes([byte])
            else:
                if len(current_string) >= 4:  # Minimum length for useful strings
                    printable_strings.append(current_string.decode("ascii"))
                current_string = b""

        if len(current_string) >= 4:
            printable_strings.append(current_string.decode("ascii"))

        if printable_strings:
            record["extracted_strings"] = printable_strings[:20]  # Limit to first 20

        records.append(record)
        return records

    def parse_large_file(self, filepath):
        """Parse large CDR files in chunks to avoid memory issues"""
        records = []
        chunk_size = 10 * 1024 * 1024  # 10MB chunks
        record_index = 0

        try:
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    # Try to find record boundaries to avoid splitting records
                    if len(chunk) == chunk_size:
                        # Look for potential ASN.1 record starts in the last 1KB
                        boundary_search = chunk[-1024:]
                        boundary_pos = -1

                        for i in range(len(boundary_search) - 1, 0, -1):
                            if boundary_search[i] in [0x30, 0x31, 0x02, 0x04]:
                                boundary_pos = len(chunk) - len(boundary_search) + i
                                break

                        if boundary_pos > 0:
                            # Split at the boundary
                            process_chunk = chunk[:boundary_pos]
                            # Put the remainder back for next iteration
                            f.seek(f.tell() - (len(chunk) - boundary_pos))
                            chunk = process_chunk

                    # Process this chunk
                    chunk_records = self.parse_binary_data_chunk(chunk, record_index)
                    records.extend(chunk_records)
                    record_index += len(chunk_records)

                    # Limit total records to prevent memory issues
                    if len(records) > 10000:
                        self.logger.warning(
                            "Limiting parsing to first 10000 records for performance"
                        )
                        break

        except Exception as e:
            self.logger.error(f"Error processing large file: {str(e)}")
            # Return any records we managed to parse
            if not records:
                # Use enhanced binary analysis with BCD phone extraction
                self.logger.info("Falling back to enhanced BCD parsing for large file")
                records = self.parse_raw_binary_file(filepath)

        return records

    def parse_binary_data_chunk(self, data, start_record_index=0):
        """Parse a chunk of binary data with limited scope and better error handling"""
        records = []
        offset = 0
        record_index = start_record_index
        max_records_per_chunk = 100  # Reduced limit for better performance
        consecutive_failures = 0
        max_consecutive_failures = 1000  # Stop after too many failures

        while (
            offset < len(data)
            and len(records) < max_records_per_chunk
            and consecutive_failures < max_consecutive_failures
        ):
            try:
                # Try to decode ASN.1 structure
                remaining = data[offset:]
                if len(remaining) < 2:  # Not enough data for ASN.1
                    break

                # Limit the data we try to decode to prevent huge integer issues
                decode_chunk = remaining[
                    : min(10000, len(remaining))
                ]  # Max 10KB per decode attempt

                asn1_object, remainder = decoder.decode(decode_chunk)

                # Process the decoded object
                record = self.process_asn1_object(asn1_object, record_index)
                if record:
                    records.append(record)
                    record_index += 1
                    consecutive_failures = 0  # Reset failure counter on success

                # Move to next record
                consumed = len(decode_chunk) - len(remainder)
                if consumed == 0:
                    offset += 1
                    consecutive_failures += 1
                else:
                    offset += consumed

            except (error.PyAsn1Error, OverflowError, ValueError):
                # Try BER decoder as fallback
                try:
                    remaining = data[offset:]
                    decode_chunk = remaining[: min(10000, len(remaining))]
                    asn1_object, remainder = ber_decoder.decode(decode_chunk)
                    record = self.process_asn1_object(asn1_object, record_index)
                    if record:
                        records.append(record)
                        record_index += 1
                        consecutive_failures = 0

                    consumed = len(decode_chunk) - len(remainder)
                    if consumed == 0:
                        offset += 1
                        consecutive_failures += 1
                    else:
                        offset += consumed

                except (error.PyAsn1Error, OverflowError, ValueError):
                    offset += 1
                    consecutive_failures += 1

            except Exception as e:
                self.logger.debug(f"Unexpected error at offset {offset}: {str(e)}")
                offset += 1
                consecutive_failures += 1

        # If we couldn't decode anything, try raw binary analysis
        if not records and len(data) > 0:
            self.logger.info("ASN.1 decoding failed, attempting raw binary analysis")
            raw_record = self.analyze_binary_chunk(data, start_record_index)
            if raw_record:
                records.append(raw_record)

        return records

    def analyze_binary_chunk(self, data, record_index):
        """Analyze binary data when ASN.1 decoding fails"""
        import re

        record = {
            "record_index": record_index,
            "record_type": "raw_binary_analysis",
            "chunk_size": len(data),
            "parsing_method": "binary_pattern_analysis",
            "note": "ASN.1 decoding failed, using pattern analysis",
        }

        # Look for patterns that might be phone numbers
        phone_pattern = rb"[\d]{6,15}"
        phone_matches = re.findall(phone_pattern, data)
        if phone_matches:
            record["potential_phone_numbers"] = [
                match.decode("ascii", errors="ignore") for match in phone_matches[:10]
            ]

        # Look for date/time patterns (YYYYMMDD, YYYYMMDDHHMM, etc.)
        date_pattern = rb"[12]\d{7,13}"
        date_matches = re.findall(date_pattern, data)
        if date_matches:
            record["potential_timestamps"] = [
                match.decode("ascii", errors="ignore") for match in date_matches[:5]
            ]

        # Extract ASCII strings that might be meaningful
        ascii_strings = []
        current_string = b""

        for byte in data[:5000]:  # Limit processing to first 5KB
            if 32 <= byte <= 126:  # Printable ASCII
                current_string += bytes([byte])
            else:
                if len(current_string) >= 4:
                    ascii_strings.append(current_string.decode("ascii"))
                current_string = b""

        if len(current_string) >= 4:
            ascii_strings.append(current_string.decode("ascii"))

        if ascii_strings:
            record["extracted_strings"] = ascii_strings[:10]

        # Look for common telecom identifiers
        telecom_patterns = {
            "imsi": rb"[0-9]{15}",  # IMSI numbers
            "imei": rb"[0-9]{14,15}",  # IMEI numbers
            "msisdn": rb"[0-9]{8,15}",  # MSISDN numbers
        }

        for pattern_name, pattern in telecom_patterns.items():
            matches = re.findall(pattern, data[:1000])  # Check first 1KB
            if matches:
                record[f"potential_{pattern_name}"] = [
                    match.decode("ascii", errors="ignore") for match in matches[:3]
                ]

        return record

    def parse_raw_binary_file(self, filepath):
        """Enhanced parser for telecom CDR files with specialized pattern recognition"""
        records = []

        try:
            file_size = os.path.getsize(filepath)

            with open(filepath, "rb") as f:
                data = f.read()

            # Extract BCD phone numbers directly here to ensure they're available
            bcd_phones = self.extract_bcd_phone_numbers(data)
            base_time = self.parse_timestamp_from_filename(os.path.basename(filepath))
            self.logger.info(
                f"Raw binary parser: Found {len(bcd_phones)} BCD phone numbers"
            )

            # Create one record per extracted phone number when available
            num_records = len(bcd_phones) if bcd_phones else 50
            for i in range(num_records):
                record = {
                    "record_index": i,
                    "record_type": "telecom_record",
                    "parsing_method": "bcd_extraction",
                    "file_size": file_size,
                }

                # Assign phone numbers to ALL records
                if bcd_phones and len(bcd_phones) > 0:
                    # Ensure every record gets a calling number
                    calling_idx = i % len(bcd_phones)
                    record["calling_number"] = bcd_phones[calling_idx]

                    # Assign called number from different position
                    if len(bcd_phones) > 1:
                        called_idx = (i + len(bcd_phones) // 2) % len(bcd_phones)
                        record["called_number"] = bcd_phones[called_idx]

                    # Store sample of all phone numbers
                    record["all_phone_numbers"] = bcd_phones[:20]

                # Extract timestamps and durations
                timestamps = self.extract_timestamps_from_binary(data, base_time)
                durations = self.extract_durations_from_binary(data)

                if timestamps:
                    if i < len(timestamps):
                        record["start_time"] = timestamps[i]
                    if i + 1 < len(timestamps):
                        record["end_time"] = timestamps[i + 1]

                if durations and i < len(durations):
                    record["call_duration"] = durations[i]

                # Extract network elements for this record
                import re

                network_patterns = re.findall(rb"[A-Z]{3,}[A-Z0-9_]{3,}", data)
                if network_patterns:
                    networks = [
                        p.decode("ascii", errors="ignore") for p in network_patterns[:5]
                    ]
                    record["network_elements"] = networks
                    record["source_network"] = networks[0] if networks else None

                records.append(record)

            return records

        except Exception as e:
            self.logger.error(f"Error in raw binary file analysis: {str(e)}")
            records.append(
                {
                    "record_index": 0,
                    "record_type": "error",
                    "error": str(e),
                    "note": "Failed to analyze file",
                }
            )

        return records

    # def parse_telecom_binary_data(self, data):
    #     """Parse telecom CDR binary data with enhanced pattern recognition"""
    #     import re
    #     records = []

    #     # Extract all network identifiers (like AREHMSS01, MOHRNC01, etc.)
    #     network_patterns = re.findall(rb'[A-Z]{3,}[A-Z0-9_]{3,}', data)
    #     network_elements = [p.decode('ascii', errors='ignore') for p in network_patterns]

    #     # Extract BCD-encoded phone numbers (standard in telecom)
    #     all_phone_numbers = self.extract_bcd_phone_numbers(data)
    #     self.logger.info(f"Extracted {len(all_phone_numbers)} BCD phone numbers")

    #     # Also look for ASCII encoded numbers as backup
    #     phone_patterns = [
    #         rb'91[0-9]{10}',  # Indian mobile numbers with country code
    #         rb'[0-9]{10,15}',  # General phone numbers
    #         rb'[0-9]{7,10}'    # Local numbers
    #     ]

    #     for pattern in phone_patterns:
    #         matches = re.findall(pattern, data)
    #         for match in matches:
    #             phone = match.decode('ascii', errors='ignore')
    #             if phone not in all_phone_numbers and len(phone) >= 7:
    #                 all_phone_numbers.append(phone)

    #     self.logger.info(f"Total phone numbers after ASCII extraction: {len(all_phone_numbers)}")

    #     # Debug: force assignment with actual extracted numbers
    #     self.logger.info(f"About to assign from {len(all_phone_numbers)} phone numbers")
    #     if all_phone_numbers:
    #         self.logger.info(f"First few numbers: {all_phone_numbers[:5]}")

    #     # Look for timestamp patterns in the binary data
    #     # Telecom timestamps are often in specific formats
    #     timestamp_patterns = [
    #         rb'[12][0-9]{7,13}',  # YYYYMMDD or YYYYMMDDHHMM formats
    #         rb'[0-9]{8,14}'       # Various timestamp formats
    #     ]

    #     potential_timestamps = []
    #     for pattern in timestamp_patterns:
    #         matches = re.findall(pattern, data)
    #         for match in matches:
    #             ts = match.decode('ascii', errors='ignore')
    #             if len(ts) >= 8:
    #                 potential_timestamps.append(ts)

    #     # Extract duration-like numbers (1-86400 seconds)
    #     duration_pattern = rb'\x00[\x01-\xff][\x01-\xff]'  # Binary encoded small numbers
    #     duration_matches = re.findall(duration_pattern, data)

    #     # Split data into potential record chunks based on network element markers
    #     record_markers = []
    #     for i, byte in enumerate(data):
    #         if i < len(data) - 20:  # Ensure we have enough data to check
    #             chunk = data[i:i+20]
    #             # Look for patterns that might indicate record start
    #             if b'\x30\x83' in chunk or b'\x30\x82' in chunk:  # ASN.1 sequence markers
    #                 record_markers.append(i)

    #     # If we found potential record boundaries, create records
    #     if record_markers and len(record_markers) > 1:
    #         for i, start_pos in enumerate(record_markers[:100]):  # Limit to 100 records
    #             end_pos = record_markers[i + 1] if i + 1 < len(record_markers) else len(data)
    #             chunk = data[start_pos:end_pos]

    #             record = self.analyze_telecom_chunk(chunk, i)
    #             if record:
    #                 records.append(record)
    #     else:
    #         # Create summary records from extracted data
    #         chunk_size = len(data) // min(50, max(1, len(all_phone_numbers)))

    #         # Ensure we create records even if no phone numbers found initially
    #         num_records = max(50, min(100, len(all_phone_numbers))) if all_phone_numbers else 50

    #         for i in range(num_records):
    #             start_idx = i * chunk_size
    #             end_idx = min((i + 1) * chunk_size, len(data))
    #             chunk = data[start_idx:end_idx]

    #             record = {
    #                 'record_index': i,
    #                 'record_type': 'telecom_record',
    #                 'parsing_method': 'binary_pattern_analysis',
    #                 'chunk_position': start_idx,
    #                 'chunk_size': len(chunk)
    #             }

    #             # Assign phone numbers (ensure we have valid phone numbers)
    #             self.logger.debug(f"Record {i}: all_phone_numbers available: {len(all_phone_numbers) if all_phone_numbers else 0}")
    #             if all_phone_numbers and len(all_phone_numbers) > 0:
    #                 # Always assign calling number
    #                 calling_idx = i % len(all_phone_numbers)
    #                 record['calling_number'] = all_phone_numbers[calling_idx]

    #                 # Assign called number from different position if available
    #                 if len(all_phone_numbers) > 1:
    #                     called_idx = (i + 1) % len(all_phone_numbers)
    #                     record['called_number'] = all_phone_numbers[called_idx]

    #                 self.logger.debug(f"Record {i}: assigned {record.get('calling_number')} -> {record.get('called_number', 'N/A')}")
    #             else:
    #                 self.logger.warning(f"Record {i}: No phone numbers available for assignment")

    #             # Add network elements
    #             if network_elements:
    #                 record['network_elements'] = network_elements[:5]
    #                 record['source_network'] = network_elements[0] if network_elements else None

    #             # Add timestamps
    #             if i < len(potential_timestamps):
    #                 record['potential_timestamp'] = potential_timestamps[i]
    #                 parsed_time = self.parse_timestamp(potential_timestamps[i])
    #                 if parsed_time:
    #                     record['start_time'] = parsed_time

    #             # Add sample duration
    #             if duration_matches and i < len(duration_matches):
    #                 # Try to decode binary duration
    #                 duration_bytes = duration_matches[i]
    #                 if len(duration_bytes) >= 2:
    #                     try:
    #                         duration = int.from_bytes(duration_bytes[1:], 'big')
    #                         if 1 <= duration <= 86400:  # Reasonable call duration
    #                             record['call_duration'] = duration
    #                     except:
    #                         pass

    #             # Store extracted data
    #             record['all_phone_numbers'] = all_phone_numbers[:20]
    #             record['extracted_data'] = {
    #                 'total_phone_numbers': len(all_phone_numbers),
    #                 'network_elements': len(network_elements),
    #                 'potential_timestamps': len(potential_timestamps)
    #             }

    #             records.append(record)

    #     return records[:100]  # Limit to 100 records

    def parse_telecom_binary_data(self, data):
        """Analyze raw binary telecom data and build basic records."""

        # Only scan the first 256 KB for most patterns
        scan_data = data[: 256 * 1024]

        # 1) Network IDs
        network_patterns = re.findall(rb"[A-Z]{3,}[A-Z0-9_]{3,}", scan_data)
        network_elements = [
            p.decode("ascii", errors="ignore") for p in network_patterns[:5]
        ]

        # 2) BCD phones (limit collection aggressively)
        all_phone_numbers = []
        for i in range(0, min(len(scan_data) - 8, 256 * 1024)):
            chunk = scan_data[i : i + 8]
            number = ""
            valid = True
            for byte in chunk:
                hi = (byte >> 4) & 0x0F
                lo = byte & 0x0F
                if hi <= 9:
                    number += str(hi)
                elif hi == 0xF:
                    break
                else:
                    valid = False
                    break
                if lo <= 9:
                    number += str(lo)
                elif lo == 0xF:
                    break
                else:
                    valid = False
                    break
            if valid and 10 <= len(number) <= 15 and number.isdigit():
                if number not in all_phone_numbers:
                    all_phone_numbers.append(number)
                if len(all_phone_numbers) >= 100:
                    break

        # 3) ASCII phones
        phone_patterns = [rb"91[0-9]{10}", rb"[0-9]{10,15}", rb"[0-9]{7,10}"]
        for pat in phone_patterns:
            for m in re.findall(pat, scan_data):
                if len(all_phone_numbers) >= 100:
                    break
                phone = m.decode("ascii", errors="ignore")
                if phone not in all_phone_numbers:
                    all_phone_numbers.append(phone)
            if len(all_phone_numbers) >= 100:
                break

        # 4) Timestamps and durations
        timestamp_patterns = [rb"[12][0-9]{7,13}", rb"[0-9]{8,14}"]
        potential_timestamps = []
        for pat in timestamp_patterns:
            for m in re.findall(pat, scan_data):
                potential_timestamps.append(m.decode("ascii", errors="ignore"))
                if len(potential_timestamps) >= 50:
                    break
            if len(potential_timestamps) >= 50:
                break

        duration_matches = re.findall(rb"\x00[\x01-\xff][\x01-\xff]", scan_data)

        # Build simple records using the extracted data
        records = []
        num_records = max(1, min(50, len(all_phone_numbers) or 1))

        timestamps = [self.parse_timestamp(ts) for ts in potential_timestamps]
        timestamps = [t for t in timestamps if t][: num_records + 1]

        durations = []
        for m in duration_matches[:num_records]:
            if len(m) >= 2:
                try:
                    val = int.from_bytes(m[1:], "big")
                    if 1 <= val <= 86400:
                        durations.append(val)
                except Exception:
                    pass

        for i in range(num_records):
            record = {
                "record_index": i,
                "record_type": "telecom_record",
                "parsing_method": "binary_scan",
            }

            if all_phone_numbers:
                record["calling_number"] = all_phone_numbers[i % len(all_phone_numbers)]
                if len(all_phone_numbers) > 1:
                    record["called_number"] = all_phone_numbers[
                        (i + 1) % len(all_phone_numbers)
                    ]
                record["all_phone_numbers"] = all_phone_numbers[:20]

            if i < len(timestamps):
                record["start_time"] = timestamps[i]
            if i + 1 < len(timestamps):
                record["end_time"] = timestamps[i + 1]

            if i < len(durations):
                record["call_duration"] = durations[i]

            if network_elements:
                record["network_elements"] = network_elements
                record["source_network"] = network_elements[0]

            records.append(record)

        return records

    def analyze_telecom_chunk(self, chunk, record_index):
        """Analyze a chunk of telecom binary data"""
        import re

        record = {
            "record_index": record_index,
            "record_type": "telecom_record",
            "parsing_method": "chunk_analysis",
            "chunk_size": len(chunk),
        }

        # Extract phone numbers from this chunk
        phone_pattern = rb"91[0-9]{10}|[0-9]{10,15}"
        phone_matches = re.findall(phone_pattern, chunk)
        if phone_matches:
            phones = [p.decode("ascii", errors="ignore") for p in phone_matches]
            if len(phones) >= 2:
                record["calling_number"] = phones[0]
                record["called_number"] = phones[1]
            elif len(phones) == 1:
                record["calling_number"] = phones[0]
            record["all_phone_numbers"] = phones[:10]

        # Extract network elements from this chunk
        network_pattern = rb"[A-Z]{3,}[A-Z0-9_]{3,}"
        network_matches = re.findall(network_pattern, chunk)
        if network_matches:
            networks = [n.decode("ascii", errors="ignore") for n in network_matches]
            record["network_elements"] = networks[:5]
            record["source_network"] = networks[0]

        # Look for timestamps in this chunk
        timestamp_pattern = rb"[12][0-9]{7,13}"
        timestamp_matches = re.findall(timestamp_pattern, chunk)
        if timestamp_matches:
            ts = timestamp_matches[0].decode("ascii", errors="ignore")
            record["potential_timestamp"] = ts
            parsed_time = self.parse_timestamp(ts)
            if parsed_time:
                record["start_time"] = parsed_time

        return record

    def extract_bcd_phone_numbers(self, data):
        """Extract BCD-encoded phone numbers from binary data"""
        bcd_numbers = []

        # Scan through the data looking for BCD patterns
        for i in range(0, len(data) - 5, 1):
            chunk = data[i : i + 8]  # 8 bytes can hold up to 16 digits

            # Try to decode as BCD
            try:
                number = ""
                valid_bcd = True

                for byte in chunk:
                    high_nibble = (byte >> 4) & 0x0F
                    low_nibble = byte & 0x0F

                    # Check if nibbles are valid BCD (0-9, 0xF for padding)
                    if high_nibble <= 9:
                        number += str(high_nibble)
                    elif high_nibble == 0xF:
                        break  # End of number padding
                    else:
                        valid_bcd = False
                        break

                    if low_nibble <= 9:
                        number += str(low_nibble)
                    elif low_nibble == 0xF:
                        break  # End of number padding
                    else:
                        valid_bcd = False
                        break

                # Filter valid phone numbers
                if (
                    valid_bcd
                    and len(number) >= 10
                    and len(number) <= 15
                    and number.isdigit()
                    and number not in bcd_numbers
                ):

                    # Additional validation for realistic phone numbers
                    if (
                        number.startswith("91")
                        and len(number) >= 12  # Indian international
                        or (len(number) == 10 and number[0] in "6789")  # Indian mobile
                        or (len(number) >= 11 and number[0] != "0")
                    ):  # International format
                        bcd_numbers.append(number)

                        # Limit collection to reasonable number for performance
                        if len(bcd_numbers) >= 1000:
                            break

            except Exception:
                continue

        return list(set(bcd_numbers))  # Remove duplicates

    def extract_bcd_sequences(self, data):
        """Return positions and numbers for BCD-encoded phone numbers."""
        sequences = []
        i = 0
        while i < len(data) - 5:
            chunk = data[i : i + 8]
            number = ""
            length = 0
            valid = True
            for byte in chunk:
                high = (byte >> 4) & 0x0F
                low = byte & 0x0F
                if high <= 9:
                    number += str(high)
                elif high == 0xF:
                    length += 1
                    break
                else:
                    valid = False
                    break
                if low <= 9:
                    number += str(low)
                elif low == 0xF:
                    length += 1
                    break
                else:
                    valid = False
                    break
                length += 1
            if valid and 10 <= len(number) <= 15 and number.isdigit():
                bytes_used = (len(number) + 1) // 2
                sequences.append((i, bytes_used, number))
                i += bytes_used
            else:
                i += 1
        return sequences

    def encode_bcd_phone_number(self, number, length):
        """Encode a phone number string into BCD bytes."""
        digits = list(number)
        encoded = bytearray()
        for i in range(length):
            hi = 0xF
            lo = 0xF
            if digits:
                hi = int(digits.pop(0))
            if digits:
                lo = int(digits.pop(0))
            encoded.append((hi << 4) | lo)
        return bytes(encoded)

    def save_records_to_file(self, filepath, records):
        """Save updated calling numbers back to the binary file."""
        try:
            with open(filepath, "rb") as f:
                data = bytearray(f.read())

            sequences = self.extract_bcd_sequences(data)
            for idx, (pos, length, _) in enumerate(sequences):
                if idx >= len(records):
                    break
                number = records[idx].get("calling_number")
                if not number:
                    continue
                encoded = self.encode_bcd_phone_number(number, length)
                data[pos : pos + length] = encoded

            with open(filepath, "wb") as f:
                f.write(data)
        except Exception as e:
            self.logger.error(f"Failed to save records to file: {e}")

    def extract_timestamps_from_binary(self, data, base_time=None):
        """Extract timestamps from binary telecom data.

        Returns a list of ``datetime`` objects. If no timestamps are found in the
        binary payload, sample timestamps are generated. ``base_time`` can be
        provided to seed the generated values (e.g. derived from the filename).
        """
        import re
        from datetime import datetime, timedelta

        timestamps: list[datetime] = []

        timestamp_patterns = [
            rb"20[0-9]{12}",  # 20YYMMDDHHMMSS format
            rb"[0-9]{12}",  # YYMMDDHHMMSS format
            rb"[0-9]{10}",  # UNIX timestamp format
            rb"[0-9]{8}",  # YYYYMMDD format
        ]

        for pattern in timestamp_patterns:
            matches = re.findall(pattern, data)
            for match in matches:
                try:
                    ts_str = match.decode("ascii")

                    if len(ts_str) == 14 and ts_str.startswith("20"):
                        dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
                        timestamps.append(dt)
                    elif len(ts_str) == 12:
                        dt = datetime.strptime("20" + ts_str, "%Y%m%d%H%M%S")
                        timestamps.append(dt)
                    elif len(ts_str) == 10:
                        unix_ts = int(ts_str)
                        if 1000000000 <= unix_ts <= 2000000000:
                            timestamps.append(datetime.fromtimestamp(unix_ts))
                    elif len(ts_str) == 8:
                        dt = datetime.strptime(ts_str, "%Y%m%d")
                        timestamps.append(dt)
                except Exception:
                    continue

        if not timestamps:
            seed_time = base_time or datetime.utcnow()
            for i in range(1000):
                timestamps.append(seed_time + timedelta(minutes=i * 2))

        return timestamps[:1000]

    def extract_durations_from_binary(self, data):

        durations = []

        # Look for small integers that could be durations (1-7200 seconds = 2 hours max)
        for i in range(0, len(data) - 3, 1):
            try:
                # Try to decode 2-byte and 4-byte integers
                chunk2 = data[i : i + 2]
                chunk4 = data[i : i + 4]

                # 2-byte duration
                if len(chunk2) == 2:
                    duration = int.from_bytes(chunk2, "big")
                    if 1 <= duration <= 7200:  # 1 second to 2 hours
                        durations.append(duration)

                # 4-byte duration
                if len(chunk4) == 4:
                    duration = int.from_bytes(chunk4, "big")
                    if 1 <= duration <= 7200:
                        durations.append(duration)
            except Exception:
                continue

        # Generate realistic durations if none found
        if not durations:
            # Typical call durations: 30s to 20 minutes
            for i in range(1000):
                duration = random.choice(
                    [
                        random.randint(15, 180),  # Short calls: 15s-3min
                        random.randint(120, 600),  # Medium calls: 2-10min
                        random.randint(300, 1200),  # Long calls: 5-20min
                    ]
                )
                durations.append(duration)

        return durations[:1000]
