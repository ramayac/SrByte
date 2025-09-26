import os
import re
import html
import argparse
import datetime
import xml.etree.ElementTree as ET

def create_slug(text: str) -> str:
    """
    Convert text to a URL-friendly slug.
    - Convert to lowercase
    - Replace spaces and special characters with hyphens
    - Remove consecutive hyphens
    - Strip leading/trailing hyphens
    """
    if not text:
        return "untitled"
    
    # Convert to lowercase and replace spaces with hyphens
    slug = text.lower()
    # Replace any non-alphanumeric character (except hyphens) with hyphens
    slug = re.sub(r'[^a-z0-9-]', '-', slug)
    # Replace multiple consecutive hyphens with a single hyphen
    slug = re.sub(r'-+', '-', slug)
    # Strip leading and trailing hyphens
    slug = slug.strip('-')
    
    # If slug is empty after processing, use default
    if not slug:
        return "untitled"
    
    # Limit length to reasonable size
    if len(slug) > 50:
        slug = slug[:50].rstrip('-')
    
    return slug

def clean_text_to_markdown(text: str) -> str:
    """
    Convert Blogger HTML content to strict Markdown.
    - Strip all HTML tags and inline styles/scripts
    - Convert common structures (headings, lists, links, images, code/pre, hr, br, blockquote, paragraphs)
    - Unescape HTML entities and normalize whitespace
    """
    if not text:
        return ""

    # Normalize newlines
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Remove script/style blocks entirely
    text = re.sub(r'<\s*(script|style)[^>]*>.*?</\s*\1\s*>', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Code blocks: <pre><code>...</code></pre> or just <pre>...</pre> -> fenced blocks
    def _pre_repl(m):
        inner = m.group(1)
        # Remove surrounding <code> if present but keep content
        inner = re.sub(r'^\s*<\s*code[^>]*>(.*?)</\s*code\s*>\s*$', r'\1', inner, flags=re.IGNORECASE | re.DOTALL)
        return '\n```\n' + inner.strip() + '\n```\n'

    text = re.sub(r'<\s*pre[^>]*>(.*?)</\s*pre\s*>', _pre_repl, text, flags=re.IGNORECASE | re.DOTALL)

    # Inline code: <code>...</code> -> `...`
    text = re.sub(r'<\s*code[^>]*>(.*?)</\s*code\s*>', lambda m: '`' + m.group(1).strip() + '`', text, flags=re.IGNORECASE | re.DOTALL)

    # Headings <h1>..</h6>
    for i in range(1, 7):
        text = re.sub(
            rf'<\s*h{i}[^>]*>(.*?)</\s*h{i}\s*>',
            lambda m, i=i: '\n' + ('#' * i) + ' ' + m.group(1).strip() + '\n',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Horizontal rule
    text = re.sub(r'<\s*hr\s*/?>', '\n---\n', text, flags=re.IGNORECASE)

    # Line breaks
    text = re.sub(r'<\s*br\s*/?>', '\n', text, flags=re.IGNORECASE)

    # Blockquote
    def _blockquote_repl(m):
        inner = m.group(1).strip()
        lines = [l.strip() for l in inner.splitlines()]
        return '\n' + '\n'.join('> ' + l for l in lines if l) + '\n'
    text = re.sub(r'<\s*blockquote[^>]*>(.*?)</\s*blockquote\s*>', _blockquote_repl, text, flags=re.IGNORECASE | re.DOTALL)

    # Lists: <ul>/<ol> with <li>
    def _ul_repl(m):
        inner = m.group(1)
        items = re.findall(r'<\s*li[^>]*>(.*?)</\s*li\s*>', inner, flags=re.IGNORECASE | re.DOTALL)
        md = '\n'.join('- ' + re.sub(r'\s+', ' ', i.strip()) for i in items)
        return '\n' + md + '\n'

    def _ol_repl(m):
        inner = m.group(1)
        items = re.findall(r'<\s*li[^>]*>(.*?)</\s*li\s*>', inner, flags=re.IGNORECASE | re.DOTALL)
        md = '\n'.join(f'{idx}. ' + re.sub(r'\s+', ' ', i.strip()) for idx, i in enumerate(items, start=1))
        return '\n' + md + '\n'

    text = re.sub(r'<\s*ul[^>]*>(.*?)</\s*ul\s*>', _ul_repl, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<\s*ol[^>]*>(.*?)</\s*ol\s*>', _ol_repl, text, flags=re.IGNORECASE | re.DOTALL)

    # Paragraphs/divs -> blank-line separated blocks
    text = re.sub(r'</\s*p\s*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*p[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</\s*div\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*div[^>]*>', '', text, flags=re.IGNORECASE)

    # Images -> ![alt](src)
    def _img_repl(m):
        attrs = m.group(0)
        src_match = re.search(r'src\s*=\s*(["\'])(.*?)\1', attrs, flags=re.IGNORECASE)
        alt_match = re.search(r'alt\s*=\s*(["\'])(.*?)\1', attrs, flags=re.IGNORECASE)
        src = src_match.group(2) if src_match else ''
        alt = alt_match.group(2) if alt_match else ''
        return f'![{alt}]({src})' if src else ''
    text = re.sub(r'<\s*img\b[^>]*>', _img_repl, text, flags=re.IGNORECASE)

    # Links -> [text](href) (use href if text is empty)
    def _a_repl(m):
        href = m.group(1) or ''
        label = m.group(2).strip()
        label_clean = re.sub(r'\s+', ' ', label)
        if not label_clean:
            label_clean = href
        return f'[{label_clean}]({href})' if href else label_clean
    text = re.sub(r'<\s*a[^>]*href\s*=\s*"([^"]*)"[^>]*>(.*?)</\s*a\s*>', lambda m: _a_repl(m), text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<\s*a[^>]*href\s*=\s*'([^']*)'[^>]*>(.*?)</\s*a\s*>", lambda m: _a_repl(m), text, flags=re.IGNORECASE | re.DOTALL)

    # Remove any remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Unescape HTML entities globally
    text = html.unescape(text)

    # Remove footer content (Blogalaxia tags and copyleft info)
    # Remove lines with blogalaxia.com links
    text = re.sub(r'\[.*?\]\(http://www\.blogalaxia\.com/tags/.*?\)', '', text)
    # Remove copyleft/copyright lines
    text = re.sub(r'Copyleft.*?Sr\. Byte', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Improve paragraph formatting by joining fragmented lines
    lines = text.splitlines()
    improved_lines = []
    current_paragraph = []
    
    for line in lines:
        line = line.rstrip()
        
        # Empty line signals end of paragraph
        if not line:
            if current_paragraph:
                # Join lines in paragraph with spaces, preserving intentional breaks
                paragraph_text = ' '.join(current_paragraph).strip()
                if paragraph_text:
                    improved_lines.append(paragraph_text)
                current_paragraph = []
            improved_lines.append('')  # Preserve empty line
        # Lines starting with special markdown (headers, lists, code fences, etc.) start new paragraphs
        elif line.startswith(('#', '-', '*', '+', '>', '```', '|')) or line.strip() in ['---', '***', '___']:
            # Finish current paragraph first
            if current_paragraph:
                paragraph_text = ' '.join(current_paragraph).strip()
                if paragraph_text:
                    improved_lines.append(paragraph_text)
                current_paragraph = []
            improved_lines.append(line)
        # Regular text lines get accumulated into current paragraph
        else:
            current_paragraph.append(line)
    
    # Handle final paragraph
    if current_paragraph:
        paragraph_text = ' '.join(current_paragraph).strip()
        if paragraph_text:
            improved_lines.append(paragraph_text)
    
    text = '\n'.join(improved_lines)
    
    # Clean up excessive whitespace
    # Convert multiple blank lines to at most two
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    # Replace multiple spaces with single spaces
    text = re.sub(r' +', ' ', text)
    # Remove trailing whitespace from lines
    text = '\n'.join(line.rstrip() for line in text.splitlines())
    
    return text.strip()

def parse_blogger_xml(file_path: str, output_dir: str = "blog_posts", include_comments: bool = False):
    """
    Parses the Blogger XML file and creates individual Markdown files for each entry.
    - If include_comments=False, entries tagged with 'http://schemas.google.com/blogger/2008/kind#comment' are skipped.
    - Each post includes YAML frontmatter with title, date, author, and tags.
    """
    # Parse the XML file
    tree = ET.parse(file_path)
    root = tree.getroot()
    
    # Namespace handling (if any)
    namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
    
    # Find all <entry> tags
    entries = root.findall('atom:entry', namespaces)
    
    # Create output directory for Markdown files
    os.makedirs(output_dir, exist_ok=True)
    
    for entry in entries:
        # Extract <id>
        entry_id = entry.find('atom:id', namespaces)
        if entry_id is None:
            continue

        # Check entry_id, it has to have the string ".post-"
        if ".post-" not in entry_id.text:
            continue

        entry_id = entry_id.text.split(':')[-1]  # Use the last part of the ID as the filename
        
        # Extract <category> terms (used for filtering and metadata)
        categories = entry.findall('atom:category', namespaces)
        category_terms = [cat.attrib.get('term', '') for cat in categories]
        
        # Skip comments unless explicitly included
        is_comment = any('blogger/2008/kind#comment' in term for term in category_terms)
        if is_comment and not include_comments:
            continue

        # Extract title
        title_element = entry.find('atom:title', namespaces)
        title = title_element.text if title_element is not None else entry_id
        
        # Extract published date
        published_element = entry.find('atom:published', namespaces)
        published_date = "2024-01-01"  # Default date
        if published_element is not None and published_element.text:
            # Parse the date and format it as YYYY-MM-DD
            try:
                # Blogger dates are in format: 2009-12-26T18:48:00.001-06:00
                dt = datetime.datetime.fromisoformat(published_element.text.replace('Z', '+00:00'))
                published_date = dt.strftime('%Y-%m-%d')
            except:
                published_date = "2024-01-01"
        
        # Extract author
        author_element = entry.find('atom:author/atom:name', namespaces)
        author = author_element.text if author_element is not None else "Unknown"
        
        # Filter and clean category terms for tags
        filtered_tags = []
        for term in category_terms:
            if not any(skip in term for skip in ['blogger/2008/kind', 'schemas.google.com']):
                filtered_tags.append(term)
        
        tags = ', '.join(filtered_tags) if filtered_tags else 'srbyte'

        # Extract <content>
        content = entry.find('atom:content', namespaces)
        if content is None:
            continue
        content_text = content.text or ''
        content_text = clean_text_to_markdown(content_text)
        
        # Create YAML frontmatter
        frontmatter = f"""---
title: {title}
date: {published_date}
author: {author}
tags: {tags}
post_id: {entry_id}
---

"""
        
        # Create Markdown content with frontmatter
        markdown_content = frontmatter + content_text
        
        # Create slug from title for filename
        title_slug = create_slug(title)
        
        # Write to a .md file with new naming convention
        output_file = os.path.join(output_dir, f"srbyte-{title_slug}.md")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"Created: {output_file}")

def bundle_markdown_files(output_dir: str = "blog_posts", bundle_path: str = "big.md", skip_comments: bool = True) -> str:
    """
    Concatenate all .md files from output_dir into a single bundle_path file.
    If skip_comments is True, any file whose content includes 'kind#comment' will be excluded.
    Returns the path to the created bundle file.
    """
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    md_files = [f for f in os.listdir(output_dir) if f.lower().endswith('.md')]
    md_files.sort()

    written = 0
    with open(bundle_path, 'w', encoding='utf-8') as out:
        for fname in md_files:
            fpath = os.path.join(output_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as inp:
                    content = inp.read().strip()
            except Exception:
                continue
            if not content:
                continue
            if skip_comments and ('blogger/2008/kind#comment' in content):
                continue
            if written:
                out.write("\n\n")
                out.write("---")
                out.write("\n\n")
            out.write(content)
            written += 1
    return bundle_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Blogger XML export to Markdown posts")
    parser.add_argument("--xml", default="srbyte.xml", help="Path to the Blogger XML file (default: srbyte.xml)")
    parser.add_argument("--out", default="blog_posts", help="Output directory for Markdown files (default: blog_posts)")
    parser.add_argument("--include-comments", action="store_true", help="Include comment entries (kind#comment) in output")
    parser.add_argument("--bundle", action="store_true", help="After generating posts, bundle all .md files into a single big.md")
    parser.add_argument("--bundle-path", default="big.md", help="Path/name for the bundled Markdown file (default: big.md)")
    args = parser.parse_args()

    parse_blogger_xml(args.xml, output_dir=args.out, include_comments=args.include_comments)
    if args.bundle:
        out_path = bundle_markdown_files(args.out, args.bundle_path, skip_comments=not args.include_comments)
        print(f"Bundled Markdown written to: {out_path}")