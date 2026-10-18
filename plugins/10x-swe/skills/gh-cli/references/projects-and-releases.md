# Historical GitHub CLI examples

Preserved from the installed January 2026 guide targeting gh 2.85.0. These examples are unverified snapshots, not current CLI contracts. Check the installed command’s `--help` before using a flag. Never print tokens, stage unrelated files, bypass checks, or perform bulk/destructive writes merely because an example shows how.

## Projects (gh project)

```bash
# List projects
gh project list

# List for owner
gh project list --owner owner

# Open projects
gh project list --open

# View project
gh project view 123

# View project items
gh project view 123 --format json

# Create project
gh project create --title "My Project"

# Create in organization
gh project create --title "Project" --org orgname

# Create with readme
gh project create --title "Project" --readme "Description here"

# Edit project
gh project edit 123 --title "New Title"

# Delete project
gh project delete 123

# Close project
gh project close 123

# Copy project
gh project copy 123 --owner target-owner --title "Copy"

# Mark template
gh project mark-template 123

# List fields
gh project field-list 123

# Create field
gh project field-create 123 --title "Status" --datatype single_select

# Delete field
gh project field-delete 123 --id 456

# List items
gh project item-list 123

# Create item
gh project item-create 123 --title "New item"

# Add item to project
gh project item-add 123 --owner-owner --repo repo --issue 456

# Edit item
gh project item-edit 123 --id 456 --title "Updated title"

# Delete item
gh project item-delete 123 --id 456

# Archive item
gh project item-archive 123 --id 456

# Link items
gh project link 123 --id 456 --link-id 789

# Unlink items
gh project unlink 123 --id 456 --link-id 789

# View project in browser
gh project view 123 --web
```

## Releases (gh release)

```bash
# List releases
gh release list

# View latest release
gh release view

# View specific release
gh release view v1.0.0

# View in browser
gh release view v1.0.0 --web

# Create release
gh release create v1.0.0 \
  --notes "Release notes here"

# Create release with notes from file
gh release create v1.0.0 --notes-file notes.md

# Create release with target
gh release create v1.0.0 --target main

# Create release as draft
gh release create v1.0.0 --draft

# Create pre-release
gh release create v1.0.0 --prerelease

# Create release with title
gh release create v1.0.0 --title "Version 1.0.0"

# Upload asset to release
gh release upload v1.0.0 ./file.tar.gz

# Upload multiple assets
gh release upload v1.0.0 ./file1.tar.gz ./file2.tar.gz

# Upload with label (casing sensitive)
gh release upload v1.0.0 ./file.tar.gz --casing

# Delete release
gh release delete v1.0.0

# Delete with cleanup tag
gh release delete v1.0.0 --yes

# Delete specific asset
gh release delete-asset v1.0.0 file.tar.gz

# Download release assets
gh release download v1.0.0

# Download specific asset
gh release download v1.0.0 --pattern "*.tar.gz"

# Download to directory
gh release download v1.0.0 --dir ./downloads

# Download archive (zip/tar)
gh release download v1.0.0 --archive zip

# Edit release
gh release edit v1.0.0 --notes "Updated notes"

# Verify release signature
gh release verify v1.0.0

# Verify specific asset
gh release verify-asset v1.0.0 file.tar.gz
```
