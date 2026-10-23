// Page information scraper for extension
// Extracts comprehensive page data including DOM structure, metadata, and content

export function getPageInfo() {
  const info = {
    url: window.location.href,
    title: document.title,
    timestamp: Date.now(),
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      scrollX: window.scrollX,
      scrollY: window.scrollY
    },
    meta: extractMetadata(),
    content: extractContent(),
    structure: extractStructure(),
    xiaohongshu: extractXiaohongshuSpecific()
  };
  
  return info;
}

function extractMetadata() {
  const meta = {};
  
  // Basic meta tags
  document.querySelectorAll('meta').forEach(tag => {
    const name = tag.getAttribute('name') || tag.getAttribute('property');
    const content = tag.getAttribute('content');
    if (name && content) {
      meta[name] = content;
    }
  });
  
  // JSON-LD structured data
  const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
  meta.jsonLd = Array.from(jsonLdScripts).map(script => {
    try {
      return JSON.parse(script.textContent);
    } catch (e) {
      return null;
    }
  }).filter(Boolean);
  
  return meta;
}

function extractContent() {
  const content = {
    headings: [],
    links: [],
    images: [],
    text: [],
    forms: []
  };
  
  // Headings
  document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
    content.headings.push({
      level: parseInt(h.tagName.substring(1)),
      text: h.textContent.trim(),
      id: h.id || null
    });
  });
  
  // Links
  document.querySelectorAll('a[href]').forEach(a => {
    content.links.push({
      text: a.textContent.trim(),
      href: a.href,
      target: a.target || null
    });
  });
  
  // Images
  document.querySelectorAll('img').forEach(img => {
    content.images.push({
      src: img.src,
      alt: img.alt || '',
      width: img.naturalWidth || img.width,
      height: img.naturalHeight || img.height
    });
  });
  
  // Main text content
  const textElements = document.querySelectorAll('p, div, span, article, section');
  textElements.forEach(el => {
    const text = el.textContent.trim();
    if (text.length > 20 && !el.querySelector('p, div')) { // Avoid nested content
      content.text.push({
        text: text.substring(0, 500), // Limit length
        tag: el.tagName.toLowerCase(),
        className: el.className || null
      });
    }
  });
  
  // Forms
  document.querySelectorAll('form').forEach(form => {
    const inputs = Array.from(form.querySelectorAll('input, textarea, select')).map(input => ({
      type: input.type || input.tagName.toLowerCase(),
      name: input.name || null,
      placeholder: input.placeholder || null,
      required: input.required
    }));
    
    content.forms.push({
      action: form.action || null,
      method: form.method || 'get',
      inputs
    });
  });
  
  return content;
}

function extractStructure() {
  return {
    totalElements: document.querySelectorAll('*').length,
    scripts: document.querySelectorAll('script').length,
    stylesheets: document.querySelectorAll('link[rel="stylesheet"]').length,
    iframes: document.querySelectorAll('iframe').length,
    bodyClasses: Array.from(document.body.classList),
    language: document.documentElement.lang || null
  };
}

function extractXiaohongshuSpecific() {
  if (!window.location.hostname.includes('xiaohongshu.com')) {
    return null;
  }
  
  const xhsData = {
    posts: [],
    userInfo: null,
    navigation: [],
    feeds: []
  };
  
  // Extract posts/notes
  document.querySelectorAll('[class*="note"], [class*="post"], [class*="card"]').forEach(el => {
    const post = {
      title: el.querySelector('[class*="title"]')?.textContent?.trim(),
      author: el.querySelector('[class*="author"], [class*="user"]')?.textContent?.trim(),
      content: el.querySelector('[class*="content"], [class*="desc"]')?.textContent?.trim(),
      image: el.querySelector('img')?.src,
      link: el.querySelector('a')?.href,
      likes: el.querySelector('[class*="like"]')?.textContent?.trim(),
      comments: el.querySelector('[class*="comment"]')?.textContent?.trim()
    };
    
    // Only add if we found meaningful content
    if (post.title || post.content || post.image) {
      xhsData.posts.push(post);
    }
  });
  
  // Extract user info if on profile page
  const userAvatar = document.querySelector('[class*="avatar"] img');
  const userName = document.querySelector('[class*="username"], [class*="nickname"]');
  if (userAvatar || userName) {
    xhsData.userInfo = {
      name: userName?.textContent?.trim(),
      avatar: userAvatar?.src,
      followers: document.querySelector('[class*="follower"]')?.textContent?.trim(),
      following: document.querySelector('[class*="following"]')?.textContent?.trim()
    };
  }
  
  // Extract navigation items
  document.querySelectorAll('nav a, [class*="nav"] a, [class*="menu"] a').forEach(link => {
    xhsData.navigation.push({
      text: link.textContent.trim(),
      href: link.href
    });
  });
  
  return xhsData;
}