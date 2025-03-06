document.addEventListener("DOMContentLoaded", function() {
  const loadingScreen = document.getElementById('loading');
  const dealsContainer = document.getElementById('deals-container');

  // Fetch deals from the API endpoint
  fetch('/api/deals')
    .then(response => response.json())
    .then(deals => {
      // Hide the loading screen and show the deals container
      loadingScreen.style.display = 'none';
      dealsContainer.style.display = 'grid';

      // Iterate over each deal and create a card
      deals.forEach(deal => {
        const card = document.createElement('div');

        // Determine the deal type based on net_profit
        let dType = 'fair';
        if (deal.net_profit !== null) {
          if (deal.net_profit < 10) {
            dType = 'fair';
          } else if (deal.net_profit < 30) {
            dType = 'good';
          } else {
            dType = 'great';
          }
        }
        card.classList.add('card');
        if (dType === 'fair') {
          card.classList.add('fair-deal-card');
        } else if (dType === 'good') {
          card.classList.add('good-deal-card');
        } else {
          card.classList.add('great-deal-card');
        }
        card.setAttribute('data-deal-type', dType);
        card.setAttribute('data-category', deal.category || '');
        card.setAttribute('data-cpu', deal.cpu_model ? deal.cpu_model : deal.title);
        card.setAttribute('data-net-profit', deal.net_profit || 0);
        card.setAttribute('data-price', deal.price);
        card.setAttribute('data-created', deal.itemCreationDate || '');

        // Determine header text based on net_profit
        let dealHeader = '';
        if (deal.net_profit !== null) {
          if (deal.net_profit < 10) {
            dealHeader = 'Fair Deal';
          } else if (deal.net_profit < 30) {
            dealHeader = 'Good Deal';
          } else {
            dealHeader = 'Great Deal';
          }
        } else {
          dealHeader = 'Low Sales Data';
        }

        // Create the card inner HTML (mirroring the Jinja template)
        card.innerHTML = `
          <div class="card-header ${
            dType === 'fair'
              ? 'fair-deal-header'
              : dType === 'good'
              ? 'good-deal-header'
              : 'great-deal-header'
          }">
            ${dealHeader}
          </div>
          <h2>${deal.cpu_model ? deal.cpu_model : deal.title}</h2>
          <p><strong>Price:</strong> $${deal.price}</p>
          <p>
            <strong>Estimated Sale Price:</strong> 
            ${deal.estimated_sale_price
              ? '$' + deal.estimated_sale_price + (deal.estimated_sale_source ? ' ' + deal.estimated_sale_source : '')
              : 'low sales data'}
          </p>
          <p>
            <strong>Net Profit:</strong> 
            ${deal.net_profit !== null ? '$' + deal.net_profit : 'low sales data'}
          </p>
          <p><strong>Condition:</strong> ${deal.condition}</p>
          <p><strong>Listed:</strong> ${deal.post_date}</p>
          <p><a href="${deal.listing_url}" target="_blank">View Listing</a></p>
        `;
        dealsContainer.appendChild(card);
      });

      // Sorting setup
      const sortSelect = document.getElementById('sort_by');
      
      sortSelect.addEventListener('change', function() {
        const criteria = this.value;
        // Get NodeList of card elements and convert to an array
        const cards = Array.from(dealsContainer.querySelectorAll('.card'));
        
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
        dealsContainer.innerHTML = "";
        sortedCards.forEach(card => dealsContainer.appendChild(card));
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
        const cards = Array.from(dealsContainer.querySelectorAll('.card'));
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
      if (sortSelect.value === "newest") {
        sortSelect.dispatchEvent(new Event('change'));
      }
    })
    .catch(error => {
      console.error('Error fetching deals:', error);
      loadingScreen.innerHTML = '<p>Error loading deals.</p>';
    });
});
