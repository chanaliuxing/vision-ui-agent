// Service worker module for collecting page information
// Integrates with the daemon system to capture comprehensive page data

export async function collectPageInfo(tabId = null) {
  try {
    // Get active tab if no tabId provided
    if (!tabId) {
      const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!activeTab) throw new Error('No active tab');
      tabId = activeTab.id;
    }

    // Inject and execute the page scraper
    const results = await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      world: 'MAIN',
      func: () => {
        // Inline the scraper function here for MV3 compatibility
        function getPageInfo() {
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
          document.querySelectorAll('meta').forEach(tag => {
            const name = tag.getAttribute('name') || tag.getAttribute('property');
            const content = tag.getAttribute('content');
            if (name && content) meta[name] = content;
          });
          
          const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
          meta.jsonLd = Array.from(jsonLdScripts).map(script => {
            try { return JSON.parse(script.textContent); } catch (e) { return null; }
          }).filter(Boolean);
          
          return meta;
        }

        function extractContent() {
          const content = { headings: [], links: [], images: [], text: [], forms: [] };
          
          // Headings
          document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
            content.headings.push({
              level: parseInt(h.tagName.substring(1)),
              text: h.textContent.trim(),
              id: h.id || null
            });
          });
          
          // Links (limit to avoid huge datasets)
          const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 100);
          links.forEach(a => {
            content.links.push({
              text: a.textContent.trim().substring(0, 100),
              href: a.href,
              target: a.target || null
            });
          });
          
          // Images (limit to avoid huge datasets)
          const images = Array.from(document.querySelectorAll('img')).slice(0, 50);
          images.forEach(img => {
            content.images.push({
              src: img.src,
              alt: img.alt || '',
              width: img.naturalWidth || img.width,
              height: img.naturalHeight || img.height
            });
          });
          
          // Text content (be selective to avoid overwhelming data)
          const textElements = Array.from(document.querySelectorAll('p, article, .content, [class*="text"], [class*="desc"]')).slice(0, 50);
          textElements.forEach(el => {
            const text = el.textContent.trim();
            if (text.length > 10 && text.length < 1000) {
              content.text.push({
                text: text,
                tag: el.tagName.toLowerCase(),
                className: el.className || null
              });
            }
          });
          
          return content;
        }

        function extractStructure() {
          return {
            totalElements: document.querySelectorAll('*').length,
            scripts: document.querySelectorAll('script').length,
            stylesheets: document.querySelectorAll('link[rel="stylesheet"]').length,
            bodyClasses: Array.from(document.body.classList),
            language: document.documentElement.lang || null
          };
        }

        function extractXiaohongshuSpecific() {
          if (!window.location.hostname.includes('xiaohongshu.com')) return null;
          
          const xhsData = { posts: [], userInfo: null, navigation: [], feeds: [] };
          
          // XHS-specific selectors (update based on actual site structure)
          const postSelectors = [
            '[class*="note"]', '[class*="post"]', '[class*="card"]',
            '.note-item', '.feed-item', '.explore-item'
          ];
          
          postSelectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => {
              const post = {
                title: el.querySelector('[class*="title"], h1, h2, h3')?.textContent?.trim(),
                author: el.querySelector('[class*="author"], [class*="user"], [class*="nickname"]')?.textContent?.trim(),
                content: el.querySelector('[class*="content"], [class*="desc"], p')?.textContent?.trim(),
                image: el.querySelector('img')?.src,
                link: el.querySelector('a')?.href || (el.tagName === 'A' ? el.href : null),
                stats: {
                  likes: el.querySelector('[class*="like"]')?.textContent?.trim(),
                  comments: el.querySelector('[class*="comment"]')?.textContent?.trim(),
                  shares: el.querySelector('[class*="share"]')?.textContent?.trim()
                }
              };
              
              if (post.title || post.content || post.image) {
                xhsData.posts.push(post);
              }
            });
          });
          
          // User info
          const userAvatar = document.querySelector('[class*="avatar"] img, .user-avatar img');
          const userName = document.querySelector('[class*="username"], [class*="nickname"], .user-name');
          if (userAvatar || userName) {
            xhsData.userInfo = {
              name: userName?.textContent?.trim(),
              avatar: userAvatar?.src,
              bio: document.querySelector('[class*="bio"], .user-desc')?.textContent?.trim(),
              stats: {
                followers: document.querySelector('[class*="follower"]')?.textContent?.trim(),
                following: document.querySelector('[class*="following"]')?.textContent?.trim(),
                posts: document.querySelector('[class*="post-count"]')?.textContent?.trim()
              }
            };
          }
          
          // Navigation
          document.querySelectorAll('nav a, [class*="nav"] a, [class*="menu"] a').forEach(link => {
            const text = link.textContent.trim();
            if (text) {
              xhsData.navigation.push({ text, href: link.href });
            }
          });
          
          return xhsData;
        }

        return getPageInfo();
      }
    });

    return results?.[0]?.result || null;
  } catch (error) {
    console.error('[PAGE_INFO] Failed to collect page info:', error);
    return { error: error.message, url: null, timestamp: Date.now() };
  }
}

// Enhanced function specifically for xiaohongshu.com feed analysis
export async function collectXiaohongshuFeed(tabId = null) {
  try {
    const pageInfo = await collectPageInfo(tabId);
    
    if (!pageInfo?.xiaohongshu) {
      throw new Error('Not a xiaohongshu.com page');
    }
    
    // Enhanced XHS-specific analysis
    const feedAnalysis = {
      ...pageInfo,
      analysis: {
        postCount: pageInfo.xiaohongshu.posts.length,
        hasUserProfile: !!pageInfo.xiaohongshu.userInfo,
        contentTypes: analyzeFeedContent(pageInfo.xiaohongshu.posts),
        engagementMetrics: calculateEngagement(pageInfo.xiaohongshu.posts),
        pageType: detectPageType(pageInfo.url, pageInfo.xiaohongshu)
      }
    };
    
    return feedAnalysis;
  } catch (error) {
    console.error('[XHS_FEED] Failed to collect XHS feed:', error);
    return { error: error.message };
  }
}

function analyzeFeedContent(posts) {
  const types = {
    withImages: 0,
    textOnly: 0,
    withLinks: 0,
    longForm: 0,
    shortForm: 0
  };
  
  posts.forEach(post => {
    if (post.image) types.withImages++;
    if (!post.image && post.content) types.textOnly++;
    if (post.link) types.withLinks++;
    if (post.content && post.content.length > 200) types.longForm++;
    else if (post.content) types.shortForm++;
  });
  
  return types;
}

function calculateEngagement(posts) {
  let totalLikes = 0;
  let totalComments = 0;
  let postsWithMetrics = 0;
  
  posts.forEach(post => {
    if (post.stats?.likes) {
      const likes = parseInt(post.stats.likes.replace(/[^\d]/g, '')) || 0;
      totalLikes += likes;
      postsWithMetrics++;
    }
    if (post.stats?.comments) {
      const comments = parseInt(post.stats.comments.replace(/[^\d]/g, '')) || 0;
      totalComments += comments;
    }
  });
  
  return {
    averageLikes: postsWithMetrics > 0 ? Math.round(totalLikes / postsWithMetrics) : 0,
    averageComments: postsWithMetrics > 0 ? Math.round(totalComments / postsWithMetrics) : 0,
    totalEngagement: totalLikes + totalComments,
    postsWithMetrics
  };
}

function detectPageType(url, xhsData) {
  if (url.includes('/user/')) return 'profile';
  if (url.includes('/explore')) return 'explore';
  if (url.includes('/search')) return 'search';
  if (xhsData.userInfo) return 'profile';
  if (xhsData.posts.length > 5) return 'feed';
  return 'unknown';
}