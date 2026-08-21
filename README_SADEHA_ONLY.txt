GITHUB REPOSITORY ONLY: videha-ejournal/videha-sadeha
Builds pagefind-videha-search/ from ordinary HTML/HTM pages for Search All Videha.
Panji records are NOT duplicated into Pagefind; Panji continues to query panji-shards/ directly.

PDF Archive addition:
- tools/build-sadeha-pdf-catalog.py scans all PDFs in videha-sadeha.
- .github/workflows/sadeha-pdf-catalog.yml builds data/sadeha-pdf-catalog.json.
- Main Videha PDF Archive federates this catalogue with videha-ejournal PDF catalogue.
