#!/usr/bin/env python3
"""
Music Folder Organizer
Organizes music files into a structured folder hierarchy based on metadata.
Supports multiple organization schemes and file operations.
"""

import os
import shutil
import sys
import argparse
from pathlib import Path
import re
from datetime import datetime
import json
from typing import Dict, List, Optional, Tuple
import subprocess
import mimetypes

try:
    from mutagen import File
    from mutagen.easyid3 import EasyID3
    from mutagen.flac import FLAC
    from mutagen.oggvorbis import OggVorbis
    from mutagen.mp4 import MP4
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("Warning: mutagen not installed. Install with: pip install mutagen")
    print("Will use filename-based organization only.")


class MusicOrganizer:
    """Organize music files into a structured directory hierarchy."""
    
    # Common audio file extensions
    AUDIO_EXTENSIONS = {
        '.mp3', '.flac', '.ogg', '.wav', '.m4a', '.aac', 
        '.wma', '.opus', '.alac', '.aiff', '.ape'
    }
    
    # Default organization schemes
    SCHEMES = {
        'artist_album': '{artist}/{album}/{track} - {title}',
        'artist_year_album': '{artist}/{year} - {album}/{track} - {title}',
        'genre_artist_album': '{genre}/{artist}/{album}/{track} - {title}',
        'album_artist': '{album_artist}/{album}/{track} - {title}',
        'year_album': '{year}/{album}/{track} - {title}',
        'simple': '{artist} - {album}/{track} - {title}',
        'flat': '{artist} - {album} - {track} - {title}'
    }
    
    def __init__(self, source_dir: str, dest_dir: str, scheme: str = 'artist_album',
                 dry_run: bool = False, copy: bool = False, 
                 organize_unknown: bool = True, clean_filenames: bool = False,
                 report_file: Optional[str] = None):
        """
        Initialize the music organizer.
        
        Args:
            source_dir: Source directory containing music files
            dest_dir: Destination directory for organized files
            scheme: Organization scheme to use
            dry_run: If True, only show what would be done
            copy: If True, copy files instead of moving
            organize_unknown: If True, organize files without metadata
            clean_filenames: If True, clean filenames (remove special chars)
            report_file: Optional path to save organization report
        """
        self.source_dir = Path(source_dir).resolve()
        self.dest_dir = Path(dest_dir).resolve()
        self.scheme = scheme
        self.dry_run = dry_run
        self.copy = copy
        self.organize_unknown = organize_unknown
        self.clean_filenames = clean_filenames
        self.report_file = report_file
        
        self.stats = {
            'total_files': 0,
            'organized': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        self.organized_files = []
        self.unknown_files = []
        
        if scheme not in self.SCHEMES:
            raise ValueError(f"Unknown scheme: {scheme}. Available: {list(self.SCHEMES.keys())}")
        
        self.pattern = self.SCHEMES[scheme]
    
    def get_metadata(self, filepath: Path) -> Dict[str, str]:
        """
        Extract metadata from audio file.
        
        Returns:
            Dictionary with metadata fields
        """
        metadata = {
            'title': 'Unknown Title',
            'artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'album_artist': 'Unknown Artist',
            'year': 'Unknown',
            'genre': 'Unknown Genre',
            'track': '0',
            'track_total': '0',
            'disc': '0',
            'disc_total': '0'
        }
        
        if not MUTAGEN_AVAILABLE:
            return metadata
        
        try:
            audio = File(filepath)
            if audio is None:
                return metadata
            
            # Extract tags based on file type
            tags = {}
            if hasattr(audio, 'tags') and audio.tags is not None:
                tags = audio.tags
            elif hasattr(audio, 'get'):
                # Handle MP4 and other formats
                for key in ['\xa9nam', '\xa9ART', '\xa9alb', 'aART', '\xa9day', '\xa9gen']:
                    if key in audio:
                        tags[key] = audio[key]
            
            # Map tags to our fields
            tag_map = {
                'title': ['TIT2', '\xa9nam', 'title'],
                'artist': ['TPE1', '\xa9ART', 'artist'],
                'album': ['TALB', '\xa9alb', 'album'],
                'album_artist': ['TPE2', 'aART', 'album_artist'],
                'year': ['TDRC', '\xa9day', 'year', 'date'],
                'genre': ['TCON', '\xa9gen', 'genre'],
                'track': ['TRCK', 'trck', 'tracknumber', 'track'],
                'track_total': ['TRCK', 'trck', 'tracktotal'],
                'disc': ['TPOS', 'disk', 'discnumber', 'disc'],
                'disc_total': ['TPOS', 'disk', 'disctotal']
            }
            
            for field, keys in tag_map.items():
                for key in keys:
                    if key in tags:
                        value = tags[key]
                        if isinstance(value, list):
                            value = value[0] if value else ''
                        # Handle special cases
                        if field in ['track', 'track_total', 'disc', 'disc_total']:
                            # Parse track/disc numbers (e.g., "2/12" or "2")
                            if isinstance(value, str) and '/' in value:
                                parts = value.split('/')
                                if field in ['track', 'disc']:
                                    metadata[field] = parts[0].strip()
                                    if len(parts) > 1:
                                        metadata[f'{field}_total'] = parts[1].strip()
                            else:
                                metadata[field] = str(value).strip()
                        else:
                            metadata[field] = str(value).strip()
                        break
            
            # Clean up track/disc numbers
            for field in ['track', 'disc']:
                try:
                    metadata[field] = int(metadata[field])
                except (ValueError, TypeError):
                    metadata[field] = 0
            
            # Try to get year from date if not available
            if metadata['year'] == 'Unknown':
                for key in ['date', 'TDRL', 'TDRC']:
                    if key in tags:
                        value = str(tags[key])
                        # Try to extract year from date string
                        year_match = re.search(r'(\d{4})', value)
                        if year_match:
                            metadata['year'] = year_match.group(1)
                            break
            
            # Handle various year formats
            if metadata['year'] and isinstance(metadata['year'], str):
                year_match = re.search(r'(\d{4})', metadata['year'])
                if year_match:
                    metadata['year'] = year_match.group(1)
            
        except Exception as e:
            # If metadata extraction fails, use filename
            pass
        
        return metadata
    
    def clean_filename(self, filename: str) -> str:
        """Clean filename by removing invalid characters and extra spaces."""
        # Remove invalid characters for filenames
        invalid_chars = r'[<>:"/\\|?*]'
        cleaned = re.sub(invalid_chars, '', filename)
        
        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Remove leading/trailing spaces and dots
        cleaned = cleaned.strip('. ')
        
        return cleaned
    
    def get_file_metadata_from_path(self, filepath: Path) -> Dict[str, str]:
        """Extract metadata from filename/path when tag extraction fails."""
        # Default metadata
        metadata = {
            'title': 'Unknown Title',
            'artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'album_artist': 'Unknown Artist',
            'year': 'Unknown',
            'genre': 'Unknown Genre',
            'track': '0'
        }
        
        # Try to parse filename
        stem = filepath.stem
        
        # Common patterns: "Artist - Album - Track - Title"
        patterns = [
            r'^(.*?)\s*-\s*(.*?)\s*-\s*(\d+)\s*-\s*(.*)$',  # Artist - Album - Track - Title
            r'^(.*?)\s*-\s*(\d+)\s*-\s*(.*)$',  # Artist - Track - Title
            r'^(\d+)\s*[-_]\s*(.*?)\s*[-_]\s*(.*)$',  # Track - Artist - Title
            r'^(.*?)\s*[-_]\s*(.*?)\s*[-_]\s*(\d+)\s*[-_]\s*(.*)$',  # Artist - Album - Track - Title (underscores)
        ]
        
        for pattern in patterns:
            match = re.match(pattern, stem)
            if match:
                groups = match.groups()
                if len(groups) == 4:
                    metadata['artist'], metadata['album'], track, metadata['title'] = groups
                    metadata['track'] = track
                elif len(groups) == 3:
                    # Try to determine which is which
                    if groups[1].isdigit():
                        metadata['artist'], metadata['track'], metadata['title'] = groups
                    else:
                        metadata['artist'], metadata['album'], metadata['title'] = groups
                break
        
        # Clean the values
        for key in metadata:
            metadata[key] = metadata[key].strip()
            if self.clean_filenames:
                metadata[key] = self.clean_filename(metadata[key])
        
        return metadata
    
    def get_destination_path(self, filepath: Path) -> Tuple[Optional[Path], Dict]:
        """Generate destination path based on organization scheme."""
        # Get metadata
        metadata = self.get_metadata(filepath)
        
        # If metadata is missing, try to get from filename
        if metadata['title'] == 'Unknown Title' or metadata['artist'] == 'Unknown Artist':
            path_metadata = self.get_file_metadata_from_path(filepath)
            # Only override if metadata is missing
            for key in ['title', 'artist', 'album', 'album_artist', 'year', 'genre', 'track']:
                if metadata[key] == 'Unknown' or metadata[key] == 'Unknown Title' or metadata[key] == 'Unknown Artist':
                    if key in path_metadata and path_metadata[key]:
                        metadata[key] = path_metadata[key]
        
        # Ensure track number is an integer
        try:
            track_num = int(metadata['track'])
        except (ValueError, TypeError):
            track_num = 0
        metadata['track'] = track_num
        
        # Format track number with leading zeros
        metadata['track_str'] = f"{track_num:02d}" if track_num > 0 else "00"
        
        # Determine if we can organize this file
        has_artist = metadata['artist'] != 'Unknown Artist'
        has_album = metadata['album'] != 'Unknown Album'
        has_title = metadata['title'] != 'Unknown Title'
        
        if not (has_artist and has_album and has_title):
            if not self.organize_unknown:
                self.stats['skipped'] += 1
                self.unknown_files.append((filepath, metadata))
                return None, metadata
        
        # Format the path using the scheme
        try:
            # Build the format dictionary
            format_dict = {
                'artist': self.clean_filename(metadata['artist']) if self.clean_filenames else metadata['artist'],
                'album_artist': self.clean_filename(metadata['album_artist']) if self.clean_filenames else metadata['album_artist'],
                'album': self.clean_filename(metadata['album']) if self.clean_filenames else metadata['album'],
                'title': self.clean_filename(metadata['title']) if self.clean_filenames else metadata['title'],
                'track': metadata['track_str'],
                'year': str(metadata['year']),
                'genre': self.clean_filename(metadata['genre']) if self.clean_filenames else metadata['genre'],
            }
            
            # Handle unknown values
            for key in ['artist', 'album_artist', 'album', 'title', 'year', 'genre']:
                if format_dict[key] == 'Unknown' or format_dict[key] == 'Unknown Artist' or \
                   format_dict[key] == 'Unknown Album' or format_dict[key] == 'Unknown Title' or \
                   format_dict[key] == 'Unknown Genre':
                    format_dict[key] = 'Unknown'
            
            # Format the path
            rel_path_str = self.pattern.format(**format_dict)
            rel_path = Path(rel_path_str)
            
            # Add file extension
            rel_path = rel_path.with_suffix(filepath.suffix)
            
            dest_path = self.dest_dir / rel_path
            
            return dest_path, metadata
            
        except KeyError as e:
            self.stats['errors'].append(f"Format error for {filepath}: {e}")
            return None, metadata
    
    def organize_file(self, filepath: Path) -> bool:
        """Organize a single file."""
        try:
            dest_path, metadata = self.get_destination_path(filepath)
            
            if dest_path is None:
                return False
            
            # Check if destination already exists
            if dest_path.exists():
                # Check if it's the same file
                if dest_path.samefile(filepath):
                    self.stats['skipped'] += 1
                    return False
                
                # Try to find a unique name
                counter = 1
                stem = dest_path.stem
                suffix = dest_path.suffix
                parent = dest_path.parent
                
                while dest_path.exists():
                    dest_path = parent / f"{stem}_{counter}{suffix}"
                    counter += 1
            
            # Create destination directory
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self.dry_run:
                print(f"Would {'copy' if self.copy else 'move'}: {filepath} -> {dest_path}")
                self.stats['organized'] += 1
                self.organized_files.append((filepath, dest_path, metadata))
                return True
            
            # Copy or move the file
            if self.copy:
                shutil.copy2(filepath, dest_path)
            else:
                shutil.move(str(filepath), str(dest_path))
            
            self.stats['organized'] += 1
            self.organized_files.append((filepath, dest_path, metadata))
            return True
            
        except Exception as e:
            self.stats['failed'] += 1
            self.stats['errors'].append(f"Error processing {filepath}: {e}")
            return False
    
    def scan_directory(self, directory: Path) -> List[Path]:
        """Recursively scan for audio files."""
        audio_files = []
        
        for root, dirs, files in os.walk(directory):
            root_path = Path(root)
            
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                file_path = root_path / file
                if file_path.suffix.lower() in self.AUDIO_EXTENSIONS:
                    audio_files.append(file_path)
                elif file_path.suffix.lower() == '.mp4':
                    # Check if it's actually audio (M4A)
                    if 'audio' in mimetypes.guess_type(file_path)[0] or 'm4a' in file.lower():
                        audio_files.append(file_path)
        
        return audio_files
    
    def generate_report(self) -> str:
        """Generate a report of the organization operation."""
        report = []
        report.append("=" * 80)
        report.append("MUSIC ORGANIZATION REPORT")
        report.append("=" * 80)
        report.append(f"Source Directory: {self.source_dir}")
        report.append(f"Destination Directory: {self.dest_dir}")
        report.append(f"Organization Scheme: {self.scheme}")
        report.append(f"Operation: {'Copy' if self.copy else 'Move'}")
        report.append(f"Dry Run: {'Yes' if self.dry_run else 'No'}")
        report.append("-" * 80)
        
        report.append(f"\nStatistics:")
        report.append(f"  Total files scanned: {self.stats['total_files']}")
        report.append(f"  Files organized: {self.stats['organized']}")
        report.append(f"  Files failed: {self.stats['failed']}")
        report.append(f"  Files skipped: {self.stats['skipped']}")
        
        if self.unknown_files:
            report.append(f"\nFiles with unknown metadata:")
            for filepath, metadata in self.unknown_files[:10]:
                report.append(f"  {filepath.name} (Artist: {metadata['artist']}, Album: {metadata['album']})")
            if len(self.unknown_files) > 10:
                report.append(f"  ... and {len(self.unknown_files) - 10} more")
        
        if self.stats['errors']:
            report.append(f"\nErrors:")
            for error in self.stats['errors'][:10]:
                report.append(f"  {error}")
            if len(self.stats['errors']) > 10:
                report.append(f"  ... and {len(self.stats['errors']) - 10} more")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)
    
    def organize(self) -> bool:
        """Run the organization process."""
        print(f"Scanning {self.source_dir} for music files...")
        
        audio_files = self.scan_directory(self.source_dir)
        self.stats['total_files'] = len(audio_files)
        
        print(f"Found {len(audio_files)} audio files")
        
        if not audio_files:
            print("No audio files found.")
            return True
        
        # Process files
        print(f"\nOrganizing files using scheme: {self.scheme}")
        for i, filepath in enumerate(audio_files, 1):
            print(f"\rProcessing: {i}/{len(audio_files)} - {filepath.name}", end='')
            self.organize_file(filepath)
        
        print(f"\n\nOrganization complete!")
        print(f"Organized: {self.stats['organized']} files")
        print(f"Failed: {self.stats['failed']} files")
        print(f"Skipped: {self.stats['skipped']} files")
        
        if self.stats['errors']:
            print(f"Errors: {len(self.stats['errors'])} errors occurred")
        
        # Generate and save report
        report = self.generate_report()
        print("\n" + report)
        
        if self.report_file:
            report_path = Path(self.report_file)
            report_path.write_text(report)
            print(f"\nReport saved to: {report_path}")
        
        return self.stats['failed'] == 0


def main():
    parser = argparse.ArgumentParser(
        description="Organize music files into a structured directory hierarchy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Organization Schemes:
  artist_album        {artist}/{album}/{track:02d} - {title}
  artist_year_album   {artist}/{year} - {album}/{track:02d} - {title}
  genre_artist_album  {genre}/{artist}/{album}/{track:02d} - {title}
  album_artist        {album_artist}/{album}/{track:02d} - {title}
  year_album          {year}/{album}/{track:02d} - {title}
  simple              {artist} - {album}/{track:02d} - {title}
  flat                {artist} - {album} - {track:02d} - {title}

Examples:
  # Organize music by artist/album structure
  python music_organizer.py ~/Music ~/Organized_Music
  
  # Copy (instead of move) and use year/album structure
  python music_organizer.py ~/Music ~/Organized_Music --scheme artist_year_album --copy
  
  # Preview what would be done without making changes
  python music_organizer.py ~/Music ~/Organized_Music --dry-run
  
  # Clean filenames and save report
  python music_organizer.py ~/Music ~/Organized_Music --clean-filenames --report report.txt
        """
    )
    
    parser.add_argument(
        'source',
        help="Source directory containing music files"
    )
    
    parser.add_argument(
        'destination',
        help="Destination directory for organized files"
    )
    
    parser.add_argument(
        '--scheme', '-s',
        default='artist_album',
        choices=list(MusicOrganizer.SCHEMES.keys()),
        help="Organization scheme to use (default: artist_album)"
    )
    
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help="Preview changes without actually moving/copying files"
    )
    
    parser.add_argument(
        '--copy', '-c',
        action='store_true',
        help="Copy files instead of moving them"
    )
    
    parser.add_argument(
        '--no-organize-unknown',
        action='store_true',
        help="Skip files that don't have complete metadata"
    )
    
    parser.add_argument(
        '--clean-filenames',
        action='store_true',
        help="Clean filenames by removing invalid characters"
    )
    
    parser.add_argument(
        '--report', '-r',
        help="Save organization report to a file"
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Show detailed output"
    )
    
    args = parser.parse_args()
    
    # Validate paths
    source_dir = Path(args.source)
    if not source_dir.exists():
        print(f"Error: Source directory '{source_dir}' does not exist.")
        sys.exit(1)
    
    if not source_dir.is_dir():
        print(f"Error: '{source_dir}' is not a directory.")
        sys.exit(1)
    
    dest_dir = Path(args.destination)
    if dest_dir.exists() and not dest_dir.is_dir():
        print(f"Error: '{dest_dir}' exists but is not a directory.")
        sys.exit(1)
    
    if not args.dry_run and source_dir == dest_dir:
        print("Error: Source and destination directories are the same. This would overwrite files.")
        sys.exit(1)
    
    # Create organizer and run
    try:
        organizer = MusicOrganizer(
            source_dir=source_dir,
            dest_dir=dest_dir,
            scheme=args.scheme,
            dry_run=args.dry_run,
            copy=args.copy,
            organize_unknown=not args.no_organize_unknown,
            clean_filenames=args.clean_filenames,
            report_file=args.report
        )
        
        success = organizer.organize()
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
