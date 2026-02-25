// ==UserScript==
// @name         Automated Exam Solver
// @namespace    http://tampermonkey.net/
// @version      1.1
// @description  Extracts multi-format questions, fetches answers from local API, and injects them into the DOM.
// @match        https://*.swayam.gov.in/*
// @grant        none
// ==/UserScript==

(async function() {
    'use strict';

    /**
     * Extracts questions from the DOM, parsing MCQ, MSQ, and numerical/text inputs.
     * @returns {Array<Object>} Array of structured question payload objects.
     */
    function extractPayload() {
        const questionContainers = document.querySelectorAll('.gcb-question-row');
        const payload = [];

        questionContainers.forEach((container, index) => {
            const questionNode = container.querySelector('.qt-question');
            const imageNode = container.querySelector('.qt-question img.yui-img');
            const choicesContainer = container.querySelector('.qt-choices');
            const responseContainer = container.querySelector('.qt-response');

            if (!questionNode) return;

            const questionText = questionNode.textContent.replace(/\s+/g, ' ').trim();
            const imageUrl = imageNode ? imageNode.src : null;
            
            let questionType = 'mcq';
            let options = [];

            if (choicesContainer) {
                const inputs = choicesContainer.querySelectorAll('input');
                if (inputs.length > 0 && inputs[0].type === 'checkbox') {
                    questionType = 'msq';
                }
                const labelNodes = choicesContainer.querySelectorAll('label');
                options = Array.from(labelNodes).map(label => label.textContent.replace(/\s+/g, ' ').trim());
            } else if (responseContainer) {
                questionType = 'numerical';
            }

            // Exclude empty questions to prevent API execution failures
            if (questionText || imageUrl) {
                payload.push({
                    question_id: index + 1,
                    question_type: questionType,
                    question_text: questionText,
                    image_url: imageUrl,
                    options: options
                });
            }
        });
        return payload;
    }

    /**
     * Injects resolved answers into the DOM based on the question type.
     * @param {Array<Object>} answers - Array of resolved answer objects.
     */
    function applyAllAnswers(answers) {
        const questionContainers = document.querySelectorAll('.gcb-question-row');
        
        answers.forEach(answer => {
            const qIndex = answer.question_id - 1;
            const container = questionContainers[qIndex];
            
            if (!container) return;

            if (answer.question_type === 'numerical') {
                const inputField = container.querySelector('.qt-response input');
                if (inputField) {
                    inputField.value = answer.text_answer;
                    // Dispatch native events to trigger framework state updates (React/Angular)
                    inputField.dispatchEvent(new Event('input', { bubbles: true }));
                    inputField.dispatchEvent(new Event('change', { bubbles: true }));
                }
            } else {
                const optionInputs = container.querySelectorAll('.gcb-mcq-choice input');
                if (!answer.option_indices) return;

                answer.option_indices.forEach(targetIndex => {
                    const targetInput = optionInputs[targetIndex];
                    if (targetInput && !targetInput.checked) {
                        targetInput.click();
                    }
                });
            }
        });
    }

    /**
     * Locates the primary submission button and triggers the native click event.
     */
    function triggerFinalSubmission() {
        const submitButton = document.getElementById('submitbutton');
        
        if (submitButton) {
            setTimeout(() => {
                submitButton.click();
                console.log("SUCCESS: Final submission triggered.");
            }, 500); 
        } else {
            console.error("CRITICAL: Submit button '#submitbutton' not found in the DOM.");
        }
    }

    /**
     * Orchestrates extraction, API transmission, and DOM injection.
     */
    async function runPipeline() {
        console.log("Initiating extraction pipeline...");
        const payload = extractPayload();

        if (payload.length === 0) {
            console.error("Extraction failed: No questions detected.");
            return;
        }

        try {
            const response = await fetch('http://127.0.0.1:5000/api/solve', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`API HTTP Error: ${response.status}`);
            }
            
            const responseData = await response.json();
            console.log("Answers resolved. Injecting into DOM...");
            console.log("Token Summary:", responseData.token_summary);
            
            applyAllAnswers(responseData.results);
            triggerFinalSubmission();
            
        } catch (error) {
            console.error("Pipeline execution failure:", error);
        }
    }

    /**
     * Binds pipeline execution to the Ctrl+Shift+S keyboard shortcut.
     */
    document.addEventListener('keydown', function(event) {
        if (event.ctrlKey && event.shiftKey && event.key === 'S') {
            runPipeline();
        }
    });
})();