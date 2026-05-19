import re
from dataclasses import dataclass
from typing import List

# Regex captures [[Target]] and handles optional sections like [[Target|Alias]] or [[Target#Heading]].
# It specifically captures the text inside the first pair of brackets (the target).
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")

@dataclass(frozen=True)
class WikiLinkRef:
    """Represents a unique resolved link reference."""
    # The target is the raw text inside [[...]], stripped of |alias and #heading parts.
    target: str

def parse_wiki_links(content: str) -> List[WikiLinkRef]:
    """
    Scans markdown content for Obsidian-style wiki links, extracts the base target, 
    and returns a de-duplicated list preserving first-occurrence order.
    Example: [[A|alias]] and [[B#head]] both resolve to A and B respectively.
    """
    found_links = []
    # Find all matches using the broad pattern
    matches = WIKI_LINK_PATTERN.findall(content)
    unique_targets = set()

    for match in matches:
        full_link = match.strip() # e.g., "A|alias" or "B#head"
        
        # Strip alias and heading to get the canonical target name
        if "|" in full_link:
            target = full_link.split("|")[0]
        elif "#" in full_link:
            target = full_link.split("#")[0]
        else:
            target = full_link

        # Only record if we haven't seen this exact target before
        if target not in unique_targets:
            found_links.append(WikiLinkRef(target=target))
            unique_targets.add(target)
            
    return found_links