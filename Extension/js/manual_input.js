class ManualJobInput {
    constructor() {
        this.form = document.getElementById('jobForm');
        this.analyzeBtn = document.getElementById('analyzeBtn');
        this.applyBtn = document.getElementById('applyBtn');
        this.generateIdBtn = document.getElementById('generateId');
        this.results = document.getElementById('results');
        this.analysisOutput = document.getElementById('analysisOutput');
        
        this.jobData = null;
        this.analysisResult = null;
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.analyzeBtn.addEventListener('click', () => this.handleAnalyze());
        this.applyBtn.addEventListener('click', () => this.handleApply());
        this.generateIdBtn.addEventListener('click', () => this.generateJobId());
    }

    gatherFormData() {
        return {
            jobId: document.getElementById('jobId').value,
            title: document.getElementById('title').value,
            company: document.getElementById('company').value,
            location: document.getElementById('location').value,
            companySize: document.getElementById('companySize').value,
            description: document.getElementById('description').value,
            requirements: document.getElementById('requirements').value,
            aboutCompany: document.getElementById('aboutCompany').value,
            glassdoorRating: {
                rating: 0,
                reviewCount: 0,
                isValid: false
            }
        };
    }

    async handleAnalyze() {
        try {
            this.jobData = this.gatherFormData();
            
            // Use chrome.runtime.sendMessage instead of direct fetch
            const response = await chrome.runtime.sendMessage({
                type: 'detailed_filter',
                data: this.jobData
            });

            this.analysisResult = response.data;
            
            // Display results
            this.results.style.display = 'block';
            this.analysisOutput.textContent = JSON.stringify(this.analysisResult, null, 2);
            
            // Enable apply button if analysis was successful
            this.applyBtn.disabled = false;
            
        } catch (error) {
            console.error('Analysis failed:', error);
            this.analysisOutput.textContent = `Error: ${error.message}`;
        }
    }

    async handleApply() {
        if (!this.jobData || !this.analysisResult) {
            alert('Please analyze the job first');
            return;
        }

        try {
            // Use chrome.runtime.sendMessage instead of direct fetch
            const response = await chrome.runtime.sendMessage({
                type: 'HANDLE_APPLY',
                data: {
                    jobId: this.jobData.jobId,
                    applyType: 'external'
                }
            });
            
            // Open editor in new tab
            if (response.editor_url) {
                window.open(response.editor_url, '_blank');
            }
            
        } catch (error) {
            console.error('Apply failed:', error);
            alert(`Apply failed: ${error.message}`);
        }
    }

    generateJobId() {
        // Generate a UUID v4 and take first 10 chars after 'M-' prefix
        const uuid = crypto.randomUUID();
        const id = `M-${uuid.replace(/-/g, '').substring(0, 10)}`;
        document.getElementById('jobId').value = id;
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    new ManualJobInput();
}); 