document.addEventListener("DOMContentLoaded", () => {

    // --- Card Animation ---
    // Stagger the animation for each card
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.animationDelay = `${index * 0.1}s`;
    });

    // --- Dark Mode Toggle ---
    const darkModeToggle = document.getElementById("darkModeToggle");
    const body = document.body;

    // Apply saved theme on load
    if (localStorage.getItem("theme") === "dark") {
        body.classList.add("dark-mode");
    }

    if(darkModeToggle) {
        darkModeToggle.addEventListener("click", () => {
            body.classList.toggle("dark-mode");
            // Save theme preference
            if (body.classList.contains("dark-mode")) {
                localStorage.setItem("theme", "dark");
            } else {
                localStorage.setItem("theme", "light");
            }
        });
    }

    // --- Customer Type Toggle for Inventory Page ---
    const typeSelect = document.getElementById('customer_type');
    const customerSelectDiv = document.getElementById('customer_select');

    if (typeSelect && customerSelectDiv) {
        typeSelect.addEventListener('change', function () {
            customerSelectDiv.style.display = (this.value === 'registered') ? 'block' : 'none';
        });
        // Initial check in case the page reloads with a selection
        customerSelectDiv.style.display = (typeSelect.value === 'registered') ? 'block' : 'none';
    }

    // --- Receipt Modal Close Function ---
    // Make closeModal globally accessible for the inline onclick attribute
    window.closeModal = function() {
        const receiptModal = document.getElementById("receiptModal");
        if (receiptModal) {
            receiptModal.style.display = "none";
            // Redirect to clean up URL and session data
            window.location.href = "{{ url_for('inventory') }}";
        }
    }
    
    // --- Toast Message Auto-hide ---
    setTimeout(() => {
        const toastMessages = document.querySelectorAll('.toast');
        toastMessages.forEach(toast => {
            toast.style.transition = 'opacity 0.5s ease';
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 500);
        });
    }, 5000); // Hide after 5 seconds
});
