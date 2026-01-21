#!/usr/bin/env python3
"""
Convert HeidelTime resource files to JSON format.

This script converts all .txt and .conf files under resources/ into
a mirrored resources_json/ directory structure with JSON files.

File types supported:
- rules: RULENAME="...",EXTRACTION="..." format with sections/groups/examples
- repattern_list: One regex pattern per line
- normalization_map: CSV-like "key","value" format
- conf_map: "key" = "value" format

Usage:
    python convert_resources_to_json.py [--input-dir INPUT] [--output-dir OUTPUT]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


def classify_file(filepath: Path, relative_path: str) -> str:
    """Classify a resource file by its path and content."""
    parts = relative_path.split(os.sep)
    
    # Classification by directory name
    if len(parts) >= 2:
        subdir = parts[1] if len(parts) > 2 else None
        if subdir == "rules":
            return "rules"
        elif subdir == "repattern":
            return "repattern_list"
        elif subdir == "normalization":
            return "normalization_map"
    
    # Classification by file extension
    if filepath.suffix == ".conf":
        return "conf_map"
    
    return "unknown"


def parse_quoted_csv_value(text: str, start: int) -> tuple[str, int]:
    """Parse a quoted value starting at position start, return (value, end_position)."""
    if start >= len(text) or text[start] != '"':
        return "", start
    
    result = []
    i = start + 1
    while i < len(text):
        if text[i] == '"':
            # Check for escaped quote
            if i + 1 < len(text) and text[i + 1] == '"':
                result.append('"')
                i += 2
            else:
                return "".join(result), i + 1
        else:
            result.append(text[i])
            i += 1
    
    # Unclosed quote, return what we have
    return "".join(result), i


def parse_rule_line(line: str) -> dict[str, str] | None:
    """
    Parse a rule line like:
    RULENAME="duration_r1a",EXTRACTION="...",NORM_VALUE="..."
    
    Returns a dict with keys in snake_case, or None if not a valid rule line.
    """
    line = line.strip()
    if not line.startswith("RULENAME="):
        return None
    
    result = {}
    i = 0
    
    while i < len(line):
        # Skip whitespace and commas
        while i < len(line) and line[i] in " ,\t":
            i += 1
        
        if i >= len(line):
            break
        
        # Find key=
        eq_pos = line.find("=", i)
        if eq_pos == -1:
            break
        
        key = line[i:eq_pos].strip()
        i = eq_pos + 1
        
        # Skip whitespace after =
        while i < len(line) and line[i] in " \t":
            i += 1
        
        if i >= len(line):
            break
        
        # Parse value (quoted or unquoted)
        if line[i] == '"':
            value, i = parse_quoted_csv_value(line, i)
        else:
            # Unquoted value - find next comma or end
            end = line.find(",", i)
            if end == -1:
                value = line[i:].strip()
                i = len(line)
            else:
                value = line[i:end].strip()
                i = end
        
        # Convert key to snake_case
        snake_key = key.lower()
        result[snake_key] = value
    
    return result if "rulename" in result else None


def parse_example_line(line: str) -> tuple[str, str] | None:
    """
    Parse an example comment line like:
    // EXAMPLE r1a-1: less than sixty days
    //EXAMPLE interval_01: from 1999 to 2012
    
    Returns (label, text) or None if not an example line.
    """
    line = line.strip()
    
    # Match various EXAMPLE formats
    patterns = [
        r"^//\s*EXAMPLE\s+(\S+):\s*(.+)$",
        r"^//\s*EXAMPLE:\s*(\S+):\s*(.+)$",
    ]
    
    for pattern in patterns:
        match = re.match(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
    
    return None


def normalize_example_label(label: str) -> str:
    """
    Normalize an example label to match rule suffixes.
    'r1a-1' -> 'r1a'
    'r5_a' -> 'r5a'
    'interval_01' -> 'interval_01'
    """
    # Strip trailing -digits
    normalized = re.sub(r"-\d+$", "", label)
    # Remove underscores (for cases like r5_a -> r5a, but keep interval_01)
    # Only remove underscores if they're followed by a single letter
    normalized = re.sub(r"_([a-zA-Z])(?![a-zA-Z0-9])", r"\1", normalized)
    return normalized


def extract_rule_suffix(rulename: str) -> str:
    """
    Extract the suffix from a rulename for example matching.
    'duration_r1a' -> 'r1a'
    'date_r0a' -> 'r0a'
    'interval_01' -> 'interval_01'
    """
    # For most rules, the suffix is after the last underscore that precedes 'r' or the end
    # e.g., duration_r1a -> r1a, date_historic_1a -> historic_1a
    
    # Try to find a suffix pattern like _rXXX or just the last part
    match = re.search(r"_(r\d+\w*)$", rulename)
    if match:
        return match.group(1)
    
    # For interval rules, match interval_XX pattern
    match = re.search(r"(interval_\d+)$", rulename)
    if match:
        return match.group(1)
    
    # Fallback: return everything after the first underscore
    parts = rulename.split("_", 1)
    return parts[1] if len(parts) > 1 else rulename


def parse_section_title(line: str) -> str | None:
    """
    Parse a section title from comment lines like:
    // POSITIVE RULES //
    /////////////////////
    // History RULES //
    
    Returns section title or None.
    """
    line = line.strip()
    
    # Match lines like "// SOMETHING RULES //" or "// SOMETHING //"
    match = re.match(r"^//+\s*([A-Z][A-Z\s\-]+[A-Z])\s*//+$", line)
    if match:
        return match.group(1).strip()
    
    # Match lines like "/////////////////////"
    if re.match(r"^/{5,}$", line):
        return None  # Just a divider, not a title
    
    return None


def parse_group_id(line: str) -> str | None:
    """
    Parse a group ID from comment lines like:
    // duration_r1
    // date_r0 (Timestamp style)
    
    Returns group ID or None.
    """
    line = line.strip()
    
    # Match lines like "// prefix_rX" or "// prefix_rX (description)"
    match = re.match(r"^//\s*(\w+_r\d+[a-z]?)(?:\s|$)", line)
    if match:
        return match.group(1)
    
    # Also match lines like "// duration_r1_negative"
    match = re.match(r"^//\s*(\w+_r\d+\w*)(?:\s|$)", line)
    if match:
        return match.group(1)
    
    return None


def parse_rules_file(filepath: Path, relative_path: str) -> dict[str, Any]:
    """Parse a rules file into structured JSON format."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    
    result = {
        "source_path": relative_path,
        "kind": "rules",
        "sections": []
    }
    
    current_section_title = "DEFAULT"
    current_group_id = None
    
    # Collect examples by normalized label
    pending_examples: dict[str, list[str]] = {}
    
    # Current section and group
    sections: dict[str, dict[str, list[dict]]] = {}
    
    for line in lines:
        line = line.rstrip("\n\r")
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            continue
        
        # Check for section title
        section_title = parse_section_title(stripped)
        if section_title:
            current_section_title = section_title
            pending_examples = {}  # Reset examples for new section
            continue
        
        # Check for group ID
        group_id = parse_group_id(stripped)
        if group_id:
            current_group_id = group_id
            pending_examples = {}  # Reset examples for new group
            continue
        
        # Check for example line
        example = parse_example_line(stripped)
        if example:
            label, text = example
            normalized = normalize_example_label(label)
            if normalized not in pending_examples:
                pending_examples[normalized] = []
            pending_examples[normalized].append(text)
            continue
        
        # Check for rule line
        rule = parse_rule_line(stripped)
        if rule:
            # Add section and group info
            rule["section_title"] = current_section_title
            rule["group_id"] = current_group_id or "ungrouped"
            
            # Match examples to this rule
            rule_suffix = extract_rule_suffix(rule["rulename"])
            rule["examples"] = pending_examples.get(rule_suffix, [])
            
            # Add to structure
            if current_section_title not in sections:
                sections[current_section_title] = {}
            
            group_key = current_group_id or "ungrouped"
            if group_key not in sections[current_section_title]:
                sections[current_section_title][group_key] = []
            
            sections[current_section_title][group_key].append(rule)
            continue
    
    # Convert to output format
    for section_title, groups in sections.items():
        section = {
            "title": section_title,
            "groups": []
        }
        for group_id, rules in groups.items():
            group = {
                "id": group_id,
                "rules": rules
            }
            section["groups"].append(group)
        result["sections"].append(section)
    
    return result


def parse_repattern_file(filepath: Path, relative_path: str) -> dict[str, Any]:
    """Parse a repattern file (one pattern per line)."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    
    patterns = []
    for line in lines:
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("//"):
            continue
        patterns.append(line)
    
    return {
        "source_path": relative_path,
        "kind": "repattern_list",
        "patterns": patterns
    }


def parse_normalization_file(filepath: Path, relative_path: str) -> dict[str, Any]:
    """Parse a normalization file (CSV-like "key","value" format)."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    
    mapping = {}
    for line in lines:
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("//"):
            continue
        
        # Parse "key","value" format
        match = re.match(r'^"([^"]*)",\s*"([^"]*)"', line)
        if match:
            mapping[match.group(1)] = match.group(2)
            continue
        
        # Try alternate format without quotes (rare)
        parts = line.split(",", 1)
        if len(parts) == 2:
            key = parts[0].strip().strip('"')
            value = parts[1].strip().strip('"')
            mapping[key] = value
    
    return {
        "source_path": relative_path,
        "kind": "normalization_map",
        "mapping": mapping
    }


def parse_conf_file(filepath: Path, relative_path: str) -> dict[str, Any]:
    """Parse a .conf file ("key" = "value" format)."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    
    mapping = {}
    for line in lines:
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("//"):
            continue
        
        # Parse "key" = "value" format
        match = re.match(r'^"([^"]+)"\s*=\s*"([^"]+)"', line)
        if match:
            mapping[match.group(1)] = match.group(2)
    
    return {
        "source_path": relative_path,
        "kind": "conf_map",
        "mapping": mapping
    }


def parse_unknown_file(filepath: Path, relative_path: str) -> dict[str, Any]:
    """Parse an unknown file type - store raw lines."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    
    return {
        "source_path": relative_path,
        "kind": "unknown",
        "raw_lines": [line.rstrip("\n\r") for line in lines]
    }


def convert_file(filepath: Path, relative_path: str) -> dict[str, Any]:
    """Convert a single resource file to JSON structure."""
    kind = classify_file(filepath, relative_path)
    
    if kind == "rules":
        return parse_rules_file(filepath, relative_path)
    elif kind == "repattern_list":
        return parse_repattern_file(filepath, relative_path)
    elif kind == "normalization_map":
        return parse_normalization_file(filepath, relative_path)
    elif kind == "conf_map":
        return parse_conf_file(filepath, relative_path)
    else:
        return parse_unknown_file(filepath, relative_path)


def convert_resources(input_dir: Path, output_dir: Path) -> dict[str, int]:
    """
    Convert all resource files from input_dir to JSON in output_dir.
    
    Returns statistics about the conversion.
    """
    stats = {
        "total_files": 0,
        "rules": 0,
        "repattern_list": 0,
        "normalization_map": 0,
        "conf_map": 0,
        "unknown": 0,
        "errors": 0
    }
    
    # Walk through all files
    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            if not (filename.endswith(".txt") or filename.endswith(".conf")):
                continue
            
            filepath = Path(root) / filename
            relative_path = str(filepath.relative_to(input_dir))
            
            # Determine output path
            output_filename = Path(filename).stem + ".json"
            output_path = output_dir / Path(relative_path).parent / output_filename
            
            try:
                # Convert file
                result = convert_file(filepath, relative_path)
                
                # Create output directory
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write JSON
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                
                stats["total_files"] += 1
                stats[result["kind"]] += 1
                
            except Exception as e:
                print(f"Error converting {relative_path}: {e}", file=sys.stderr)
                stats["errors"] += 1
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Convert HeidelTime resource files to JSON format."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).parent.parent / "resources",
        help="Input resources directory (default: ../resources)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "resources_json",
        help="Output JSON directory (default: ../resources_json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    if args.dry_run:
        print(f"Would convert files from: {input_dir}")
        print(f"Would write output to: {output_dir}")
        
        # Count files
        count = 0
        for root, dirs, files in os.walk(input_dir):
            for filename in files:
                if filename.endswith(".txt") or filename.endswith(".conf"):
                    count += 1
        print(f"Found {count} resource files to convert")
        return
    
    print(f"Converting resources from: {input_dir}")
    print(f"Writing output to: {output_dir}")
    
    stats = convert_resources(input_dir, output_dir)
    
    print("\nConversion complete!")
    print(f"  Total files: {stats['total_files']}")
    print(f"  Rules: {stats['rules']}")
    print(f"  Repattern lists: {stats['repattern_list']}")
    print(f"  Normalization maps: {stats['normalization_map']}")
    print(f"  Conf maps: {stats['conf_map']}")
    print(f"  Unknown: {stats['unknown']}")
    if stats["errors"] > 0:
        print(f"  Errors: {stats['errors']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
