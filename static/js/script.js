// Wait until the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function () {
    
    const form = document.querySelector('form');  // Select the form
    form.addEventListener('submit', function (event) {
        event.preventDefault();  // Prevent the form from submitting immediately
        
        // Get the form values
        const name = document.getElementById('name').value;
        const email = document.getElementById('email').value;
        const service = document.getElementById('service').value;
        const budget = document.getElementById('budget').value;
        const location = document.getElementById('location').value;
        const requests = document.getElementById('requests').value;

        // Check if all fields are filled
        if (!name || !email || !service || !budget) {
            alert("Please fill out all required fields.");
            return;
        }

        // If everything is okay, display a success message
        alert(`Thank you for your submission, ${name}!\nWe will get back to you regarding the ${service} service.`);

        // Optionally, you can clear the form after submission
        form.reset();
    });
});