(function() {
    'use strict';

    function extractPayload() {
        const questionContainers = document.querySelectorAll('.gcb-question-row');
        const payload = [];

        questionContainers.forEach((container, index) => {
            const questionNode = container.querySelector('.qt-question');
            const imageNode = container.querySelector('.qt-question img.yui-img');
            const choicesContainer = container.querySelector('.qt-choices');
            const responseContainer = container.querySelector('.qt-response');

            if (!questionNode) return;

            const parentGroup = container.closest('.qt-question-group');
            let caseStudyText = "";
            
            if (parentGroup) {
                const introNode = parentGroup.querySelector('.qt-introduction');
                if (introNode) {
                    caseStudyText = introNode.textContent.replace(/\s+/g, ' ').trim();
                }
            }

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

            if (questionText || imageUrl) {
                payload.push({
                    question_id: index + 1,
                    question_type: questionType,
                    question_text: questionText,
                    case_study_text: caseStudyText,
                    image_url: imageUrl,
                    options: options
                });
            }
        });
        return payload;
    }

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

    function runPipeline() {
        console.log("Initiating extraction pipeline...");
        const payload = extractPayload();

        if (payload.length === 0) {
            console.error("Extraction failed: No questions detected.");
            return;
        }

        chrome.runtime.sendMessage({ action: "SOLVE_EXAM", payload: payload }, (response) => {
            if (chrome.runtime.lastError) {
                console.error("Message dispatch failure:", chrome.runtime.lastError);
                return;
            }

            if (response && response.success) {
                console.log("Answers resolved. Injecting into DOM...");
                console.log("Token Summary:", response.data.token_summary);
                applyAllAnswers(response.data.results);
                triggerFinalSubmission();
            } else {
                console.error("Pipeline API failure:", response.error);
            }
        });
    }

    document.addEventListener('keydown', function(event) {
        if (event.ctrlKey && event.shiftKey && event.key === 'S') {
            runPipeline();
        }
    });
})();