document.addEventListener("DOMContentLoaded", function() {
    // Sorting setup
    const sortSelect = document.getElementById('sort_by');
    const container = document.querySelector('.container');
    
    sortSelect.addEventListener('change', function() {
      const criteria = this.value;
      // Get NodeList of card elements and convert to an array
      const cards = Array.from(container.querySelectorAll('.card'));
      
      let sortedCards;
      
      if (criteria === 'newest') {
        // Sort by creation date descending (newest first)
        sortedCards = cards.sort((a, b) => {
          let dateA = new Date(a.dataset.created);
          let dateB = new Date(b.dataset.created);
          return dateB - dateA;
        });
      } else if (criteria === 'deal_type') {
        // Custom order for deal type: great, good, fair, then low sales data
        const order = { 'great': 0, 'good': 1, 'fair': 2, 'low': 3 };
        sortedCards = cards.sort((a, b) => {
          return order[a.dataset.dealType] - order[b.dataset.dealType];
        });
      } else if (criteria === 'cpu') {
        sortedCards = cards.sort((a, b) => {
          const cpuA = a.dataset.cpu.toLowerCase();
          const cpuB = b.dataset.cpu.toLowerCase();
          return cpuA.localeCompare(cpuB);
        });
      } else if (criteria === 'net_profit') {
        sortedCards = cards.sort((a, b) => {
          return parseFloat(b.dataset.netProfit) - parseFloat(a.dataset.netProfit);
        });
      } else if (criteria === 'price_asc') {
        sortedCards = cards.sort((a, b) => {
          return parseFloat(a.dataset.price) - parseFloat(b.dataset.price);
        });
      } else if (criteria === 'price_desc') {
        sortedCards = cards.sort((a, b) => {
          return parseFloat(b.dataset.price) - parseFloat(a.dataset.price);
        });
      } else {
        return;
      }
      
      // Remove all cards from container and append sorted cards
      container.innerHTML = "";
      sortedCards.forEach(card => container.appendChild(card));
    });
    
    // Filtering setup
    const filterForm = document.getElementById('filter_form');
    const categoryCheckboxes = document.querySelectorAll('input[name="category"]');
    const dealTypeCheckboxes = document.querySelectorAll('input[name="deal_type"]');
    
    // Prevent the form from submitting
    filterForm.addEventListener('submit', function(e) {
      e.preventDefault();
      applyFilters();
    });
    
    // Also apply filters when any checkbox changes
    categoryCheckboxes.forEach(checkbox => checkbox.addEventListener('change', applyFilters));
    dealTypeCheckboxes.forEach(checkbox => checkbox.addEventListener('change', applyFilters));
    
    function applyFilters() {
      // Get selected category values (lowercase)
      const selectedCategories = Array.from(categoryCheckboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value.toLowerCase());
        
      // Get selected deal type values (lowercase)
      const selectedDealTypes = Array.from(dealTypeCheckboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value.toLowerCase());
        
      // Filter cards based on the selections
      const cards = Array.from(container.querySelectorAll('.card'));
      cards.forEach(card => {
        const cardCategory = card.getAttribute('data-category').toLowerCase();
        const cardDealType = card.getAttribute('data-deal-type').toLowerCase();
        
        // If checkboxes are selected, then card must match; if none selected, consider it a match
        let categoryMatch = selectedCategories.length === 0 || selectedCategories.includes(cardCategory);
        let dealTypeMatch = selectedDealTypes.length === 0 || selectedDealTypes.includes(cardDealType);
        
        card.style.display = (categoryMatch && dealTypeMatch) ? "" : "none";
      });
    }
    
    // Trigger default sort on page load (Newest Listings)
    if(sortSelect.value === "newest"){
      sortSelect.dispatchEvent(new Event('change'));
    }
});
