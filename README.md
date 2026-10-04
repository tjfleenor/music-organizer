# Music Organizer

A Python CLI tool that organizes your music collection into a structured folder hierarchy based on audio metadata (ID3 tags, Vorbis comments, etc.).

## Features

- **Multiple organization schemes** — artist/album, year/album, genre/artist, flat, and more
- **Metadata extraction** — reads tags from MP3, FLAC, OGG, M4A, WAV, and other formats via [mutagen](https://mutagen.readthedocs.io/)
- **Filename fallback** — parses common filename patterns when tags are missing
- **Dry-run mode** — preview changes before committing
- **Copy or move** — choose to copy files or move them
- **Duplicate handling** — auto-renames on collision
- **Report generation** — save a summary of what was done

## Installation

```bash
git clone https://github.com/tjfleenor/music-organizer.git
cd music-organizer
pip install mutagen
```

## Usage

```bash
# Basic — organize by artist/album
python music_organizer.py ~/Music ~/Organized_Music

# Preview first (dry run)
python music_organizer.py ~/Music ~/Organized_Music --dry-run

# Copy instead of move, with year/album structure
python music_organizer.py ~/Music ~/Organized_Music --scheme artist_year_album --copy

# Clean filenames and save a report
python music_organizer.py ~/Music ~/Organized_Music --clean-filenames --report report.txt
```

## Organization Schemes

| Scheme | Pattern |
|--------|---------|
| `artist_album` | `{artist}/{album}/{track} - {title}` |
| `artist_year_album` | `{artist}/{year} - {album}/{track} - {title}` |
| `genre_artist_album` | `{genre}/{artist}/{album}/{track} - {title}` |
| `album_artist` | `{album_artist}/{album}/{track} - {title}` |
| `year_album` | `{year}/{album}/{track} - {title}` |
| `simple` | `{artist} - {album}/{track} - {title}` |
| `flat` | `{artist} - {album} - {track} - {title}` |

## Requirements

- Python 3.7+
- [mutagen](https://pypi.org/project/mutagen/) — for reading audio metadata

## License

MIT
