document.getElementById('addBlacklist').onclick = async () => {
    const result = document.getElementById('blacklistResult');
    try {
        const response = await chrome.runtime.sendMessage({
            type: 'add_to_blacklist',
            data: { company: 'Test Company', reason: 'Test reason' }
        });

        if (response?.status === 'error') {
            throw new Error(response.error);
        }

        // Wait for storage update before reading
        await new Promise((resolve) => {
            const listener = (changes) => {
                if (changes.blacklist) {
                    chrome.storage.onChanged.removeListener(listener);
                    resolve();
                }
            };
            chrome.storage.onChanged.addListener(listener);
        });

        const { blacklist } = await chrome.storage.local.get('blacklist');
        result.textContent = JSON.stringify(blacklist || [], null, 2);
    } catch (e) {
        result.textContent = `Error: ${e.message}`;
    }
};

document.getElementById('removeBlacklist').onclick = async () => {
    const result = document.getElementById('blacklistResult');
    try {
        const response = await chrome.runtime.sendMessage({
            type: 'remove_from_blacklist',
            data: { company: 'Test Company' }
        });

        if (response?.status === 'error') {
            throw new Error(response.error);
        }

        // Wait for storage update before reading
        await new Promise((resolve) => {
            const listener = (changes) => {
                if (changes.blacklist) {
                    chrome.storage.onChanged.removeListener(listener);
                    resolve();
                }
            };
            chrome.storage.onChanged.addListener(listener);
        });

        const { blacklist } = await chrome.storage.local.get('blacklist');
        result.textContent = JSON.stringify(blacklist || [], null, 2);
    } catch (e) {
        result.textContent = `Error: ${e.message}`;
    }
};

document.getElementById('checkBlacklist').onclick = async () => {
    const result = document.getElementById('blacklistResult');
    const storage = await chrome.storage.local.get('blacklist');
    result.textContent = JSON.stringify(storage.blacklist || [], null, 2);
};

document.getElementById('checkHistory').onclick = async () => {
    const result = document.getElementById('historyResult');
    const storage = await chrome.storage.local.get('job_history');
    result.textContent = JSON.stringify(storage.job_history || [], null, 2);
}; 