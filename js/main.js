document.addEventListener("DOMContentLoaded", () => {
    const ctaButton = document.getElementById("cta-button");
    ctaButton.addEventListener("click", () => {
        document.getElementById("features").scrollIntoView({ behavior: "smooth" });
    });

    const contactForm = document.getElementById("contact-form");
    contactForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(contactForm));
        console.log("Form submitted:", data);
        contactForm.reset();
        alert("Thanks for reaching out! (This is a demo — no data was sent.)");
    });

    // Theme toggle
    const themeSwitch = document.getElementById("theme-switch");
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme) {
        document.documentElement.setAttribute("data-theme", savedTheme);
        themeSwitch.checked = savedTheme === "light";
    }
    themeSwitch.addEventListener("change", () => {
        const theme = themeSwitch.checked ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem("theme", theme);
    });

    // Animate cards on scroll
    const cards = document.querySelectorAll(".card");
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = "1";
                    entry.target.style.transform = "translateY(0)";
                }
            });
        },
        { threshold: 0.1 }
    );

    cards.forEach((card) => {
        card.style.opacity = "0";
        card.style.transform = "translateY(20px)";
        card.style.transition = "opacity 0.4s ease, transform 0.4s ease";
        observer.observe(card);
    });
});
