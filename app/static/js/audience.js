document.addEventListener('DOMContentLoaded', function() {
    const postsContainer = document.getElementById('posts-container');
    const subreddits = JSON.parse(document.getElementById('subreddit-list').dataset.subreddits);
    
    async function loadPosts() {
        for (const subreddit of subreddits) {
            try {
                const response = await fetch(`/api/posts/${subreddit.name}`);
                const data = await response.json();
                
                data.posts.forEach(post => {
                    const postEl = document.createElement('div');
                    postEl.className = 'post-card';
                    postEl.innerHTML = `
                        <h3>${post.title}</h3>
                        <p>Score: ${post.score}</p>
                        <a href="${post.url}" target="_blank">Read More</a>
                    `;
                    postsContainer.appendChild(postEl);
                });
                
            } catch (error) {
                console.error(`Error loading posts for ${subreddit.name}:`, error);
            }
            
            // Rate limiting
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }
    
    loadPosts();
});