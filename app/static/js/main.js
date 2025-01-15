// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // Search functionality
    const searchInput = document.getElementById('audience-search');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(handleSearch, 300));
    }

    // Initialize filters
    initializeFilters();
});

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function handleSearch(event) {
    const searchTerm = event.target.value.toLowerCase();
    const audienceCards = document.querySelectorAll('.audience-card');

    audienceCards.forEach(card => {
        const title = card.querySelector('h3').textContent.toLowerCase();
        const subreddit = card.querySelector('.subreddit').textContent.toLowerCase();
        
        if (title.includes(searchTerm) || subreddit.includes(searchTerm)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

function initializeFilters() {
    const filterLinks = document.querySelectorAll('.filter-section a');
    filterLinks.forEach(link => {
        link.addEventListener('click', handleFilterClick);
    });
}

function handleFilterClick(event) {
    event.preventDefault();
    const url = new URL(window.location);
    const param = event.target.href.split('?')[1].split('=')[0];
    const value = event.target.href.split('=')[1];
    
    url.searchParams.set(param, value);
    window.location.href = url.toString();
}

async function saveAudience(audience) {
    try {
        const response = await fetch('/api/audiences/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(audience)
        });
        
        if (response.ok) {
            alert('Audience saved successfully!');
        } else {
            throw new Error('Failed to save audience');
        }
    } catch (error) {
        console.error('Error saving audience:', error);
        alert('Error saving audience. Please try again.');
    }
}

function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 p-4 rounded-lg ${
        type === 'success' ? 'bg-green-500' : 'bg-red-500'
    } text-white`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 3000);
}

async function searchSubreddits(query) {
    const response = await fetch(`/audience/search?q=${encodeURIComponent(query)}`);
    const results = await response.json();
    displaySearchResults(results);
}

async function saveSubreddit(subredditName) {
    try {
        const response = await fetch(`/audience/fetch-subreddit?name=${subredditName}`);
        const subredditData = await response.json();
        
        const saveResponse = await fetch('/audience/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(subredditData)
        });
        
        if (saveResponse.ok) {
            alert('Subreddit saved successfully!');
            window.location.reload();
        } else {
            const error = await saveResponse.json();
            alert(error.error || 'Failed to save subreddit');
        }
    } catch (error) {
        alert('Error saving subreddit');
    }
}

async function saveAllAsAudience() {
    const interests = document.getElementById('interests').value;
    const subredditsElements = document.querySelectorAll('.subreddit-card');
    
    if (!interests || subredditsElements.length === 0) {
        showNotification('Please enter interests and select subreddits', 'error');
        return;
    }
    
    const subreddits = Array.from(subredditsElements).map(element => ({
        name: element.dataset.subreddit,
        subscribers: parseInt(element.dataset.subscribers),
        description: element.dataset.description
    }));

    try {
        const response = await fetch('/api/audiences/bulk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify({
                interests: interests,
                subreddits: subreddits
            })
        });

        const data = await response.json();
        
        if (response.ok) {
            showNotification('Audience saved successfully!', 'success');
            setTimeout(() => {
                window.location.href = data.redirect || '/dashboard';
            }, 1000);
        } else {
            throw new Error(data.error || 'Failed to save audience');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification(error.message, 'error');
    }
}

async function handleSaveAll() {
    try {
        const interests = document.getElementById('interestInput').value;
        const subredditsElements = document.querySelectorAll('.subreddit-card');
        
        if (!interests) {
            alert('Please enter interests first');
            return;
        }
        
        const subreddits = Array.from(subredditsElements).map(element => ({
            name: element.dataset.subreddit,
            subscribers: parseInt(element.dataset.subscribers),
            description: element.dataset.description
        }));

        const response = await fetch('/api/audiences/bulk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify({
                interests: interests,
                subreddits: subreddits
            })
        });

        const data = await response.json();
        
        if (response.ok) {
            window.location.href = '/dashboard';
        } else {
            throw new Error(data.error || 'Failed to save audience');
        }
    } catch (error) {
        console.error('Error:', error);
        alert(error.message);
    }
}