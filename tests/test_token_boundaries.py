"""
Tests for token boundary checking in HeidelTime.

These tests verify that temporal expressions are correctly extracted when
followed by various punctuation characters, particularly commas.

Bug context:
    When HeidelTime encounters text like "March 9, imprisoned", it should
    extract "March 9" as the date. Previously, it only extracted "March"
    because the comma was not in the allowed boundary character set in
    _check_token_boundaries().
"""
import os
import sys
import pytest

# Ensure the parent directory is in the path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heideltime_engine import HeidelTimeEngine
from comprehend_preprocessor import Sentence, Token


# Set up resources directory
RESOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")


def create_mock_sentence(text: str, offset: int = 0) -> Sentence:
    """
    Create a mock sentence with simple tokenization for testing.
    
    This simulates how AWS Comprehend tokenizes text by separating:
    - Words (alphabetic sequences)
    - Numbers (digit sequences)
    - Punctuation (individual characters)
    """
    tokens = []
    token_id = 1
    i = 0
    while i < len(text):
        # Skip whitespace
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        
        # Find token end
        start = i
        if text[i].isalpha():
            # Word token
            while i < len(text) and text[i].isalpha():
                i += 1
        elif text[i].isdigit():
            # Number token
            while i < len(text) and text[i].isdigit():
                i += 1
        else:
            # Punctuation token
            i += 1
        
        tokens.append(Token(
            text=text[start:i],
            begin=offset + start,
            end=offset + i,
            pos="",
            token_id=token_id,
        ))
        token_id += 1
    
    return Sentence(
        text=text,
        begin=offset,
        end=offset + len(text),
        tokens=tokens,
    )


@pytest.fixture
def engine():
    """Create a HeidelTime engine for testing."""
    return HeidelTimeEngine(
        language_dir=os.path.join(RESOURCES_DIR, "english"),
        use_pos=False,
    )


class TestCommaBoundary:
    """Tests for comma boundary handling in date extraction."""
    
    def test_month_day_comma(self, engine):
        """
        Test that 'March 9, imprisoned' extracts 'March 9', not just 'March'.
        
        Bug: Previously, HeidelTime only extracted "March" when followed by
        a comma because commas were not in the allowed boundary character set.
        """
        text = "March 9, imprisoned"
        sentences = [create_mock_sentence(text)]
        
        timexes = engine.extract(text, sentences=sentences)
        date_timexes = [t for t in timexes if t.timex_type == "DATE"]
        
        assert len(date_timexes) == 1, f"Expected 1 date, got {len(date_timexes)}"
        assert date_timexes[0].text == "March 9", \
            f"Expected 'March 9', got '{date_timexes[0].text}'"
    
    def test_month_year_comma(self, engine):
        """
        Test that 'February 2019, something' extracts 'February 2019'.
        """
        text = "February 2019, something happened"
        sentences = [create_mock_sentence(text)]
        
        timexes = engine.extract(text, sentences=sentences)
        date_timexes = [t for t in timexes if t.timex_type == "DATE"]
        
        assert len(date_timexes) >= 1, "Expected at least 1 date"
        found_texts = [t.text for t in date_timexes]
        assert "February 2019" in found_texts, \
            f"Expected 'February 2019' in {found_texts}"
    
    def test_full_date_comma(self, engine):
        """
        Test that 'January 15, 2024, the meeting' extracts 'January 15, 2024'.
        """
        text = "January 15, 2024, the meeting started"
        sentences = [create_mock_sentence(text)]
        
        timexes = engine.extract(text, sentences=sentences)
        date_timexes = [t for t in timexes if t.timex_type == "DATE"]
        
        assert len(date_timexes) >= 1, "Expected at least 1 date"
        # The full date should be extracted
        found_texts = [t.text for t in date_timexes]
        assert any("January 15" in t for t in found_texts), \
            f"Expected date with 'January 15' in {found_texts}"


class TestOtherBoundaries:
    """Tests for other boundary characters."""
    
    def test_date_space_boundary(self, engine):
        """Control test: dates with space boundaries should work."""
        text = "March 9 political event"
        sentences = [create_mock_sentence(text)]
        
        timexes = engine.extract(text, sentences=sentences)
        date_timexes = [t for t in timexes if t.timex_type == "DATE"]
        
        assert len(date_timexes) == 1
        assert date_timexes[0].text == "March 9"
    
    def test_date_period_boundary(self, engine):
        """Test that dates followed by periods are extracted correctly."""
        text = "It happened on March 9. The next day was different."
        sentences = [create_mock_sentence(text)]
        
        timexes = engine.extract(text, sentences=sentences)
        date_timexes = [t for t in timexes if t.timex_type == "DATE"]
        
        assert len(date_timexes) >= 1
        found_texts = [t.text for t in date_timexes]
        assert "March 9" in found_texts, f"Expected 'March 9' in {found_texts}"
    
    def test_date_at_sentence_start(self, engine):
        """Test dates at the beginning of a sentence."""
        text = "March 9 was a significant day"
        sentences = [create_mock_sentence(text)]
        
        timexes = engine.extract(text, sentences=sentences)
        date_timexes = [t for t in timexes if t.timex_type == "DATE"]
        
        assert len(date_timexes) == 1
        assert date_timexes[0].text == "March 9"


class TestMultipleDatesWithCommas:
    """Tests for documents with multiple dates separated by commas."""
    
    def test_date_list(self, engine):
        """Test multiple dates in a comma-separated list."""
        text = "The events occurred on March 9, April 10, and May 11"
        sentences = [create_mock_sentence(text)]
        
        timexes = engine.extract(text, sentences=sentences)
        date_timexes = [t for t in timexes if t.timex_type == "DATE"]
        
        found_texts = [t.text for t in date_timexes]
        # Should find at least some of these dates
        assert len(date_timexes) >= 2, \
            f"Expected at least 2 dates, found: {found_texts}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
