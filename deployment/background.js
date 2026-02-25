chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "SOLVE_EXAM") {
        fetch('http://127.0.0.1:5000/api/solve', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(request.payload)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`API HTTP Error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            sendResponse({ success: true, data: data });
        })
        .catch(error => {
            console.error("Background fetch error:", error);
            sendResponse({ success: false, error: error.message });
        });

        return true; 
    }
});