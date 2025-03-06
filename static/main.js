document.addEventListener("DOMContentLoaded", async function() {
  const loadingScreen = document.getElementById('loading');
  const dealsContainer = document.getElementById('deals-container');

  // Helper: create a card element from a deal object.
  function createDealCard(deal) {
    const card = document.createElement('div');
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
    return card;
  }

  // Stream deals using fetch and process the response as a stream.
  async function streamDeals() {
    const response = await fetch('/api/deals/stream');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let lines = buffer.split("\n");
      buffer = lines.pop(); // last element might be incomplete
      for (let line of lines) {
        if (line.trim()) {
          try {
            const deal = JSON.parse(line);
            const card = createDealCard(deal);
            dealsContainer.appendChild(card);
            // Hide the loading screen once the first card is added.
            if (dealsContainer.childElementCount === 1) {
              loadingScreen.style.display = 'none';
              dealsContainer.style.display = 'grid';
            }
          } catch (err) {
            console.error("Error parsing deal:", line, err);
          }
        }
      }
    }
  }

  streamDeals().catch(error => {
    console.error('Error streaming deals:', error);
    loadingScreen.innerHTML = '<p>Error loading deals.</p>';
  });

  // Sorting and Filtering Setup (same as before)
  const sortSelect = document.getElementById('sort_by');
  sortSelect.addEventListener('change', function() {
    const criteria = this.value;
    const cards = Array.from(dealsContainer.querySelectorAll('.card'));
    let sortedCards;
    if (criteria === 'newest') {
      sortedCards = cards.sort((a, b) => {
        let dateA = new Date(a.dataset.created);
        let dateB = new Date(b.dataset.created);
        return dateB - dateA;
      });
    } else if (criteria === 'deal_type') {
      const order = { 'great': 0, 'good': 1, 'fair': 2, 'low': 3 };
      sortedCards = cards.sort((a, b) => order[a.dataset.dealType] - order[b.dataset.dealType]);
    } else if (criteria === 'cpu') {
      sortedCards = cards.sort((a, b) => {
        const cpuA = a.dataset.cpu.toLowerCase();
        const cpuB = b.dataset.cpu.toLowerCase();
        return cpuA.localeCompare(cpuB);
      });
    } else if (criteria === 'net_profit') {
      sortedCards = cards.sort((a, b) => parseFloat(b.dataset.netProfit) - parseFloat(a.dataset.netProfit));
    } else if (criteria === 'price_asc') {
      sortedCards = cards.sort((a, b) => parseFloat(a.dataset.price) - parseFloat(b.dataset.price));
    } else if (criteria === 'price_desc') {
      sortedCards = cards.sort((a, b) => parseFloat(b.dataset.price) - parseFloat(a.dataset.price));
    } else {
      return;
    }
    dealsContainer.innerHTML = "";
    sortedCards.forEach(card => dealsContainer.appendChild(card));
  });

  const filterForm = document.getElementById('filter_form');
  const categoryCheckboxes = document.querySelectorAll('input[name="category"]');
  const dealTypeCheckboxes = document.querySelectorAll('input[name="deal_type"]');
  
  filterForm.addEventListener('submit', function(e) {
    e.preventDefault();
    applyFilters();
  });
  categoryCheckboxes.forEach(checkbox => checkbox.addEventListener('change', applyFilters));
  dealTypeCheckboxes.forEach(checkbox => checkbox.addEventListener('change', applyFilters));
  
  function applyFilters() {
    const selectedCategories = Array.from(categoryCheckboxes)
      .filter(cb => cb.checked)
      .map(cb => cb.value.toLowerCase());
    const selectedDealTypes = Array.from(dealTypeCheckboxes)
      .filter(cb => cb.checked)
      .map(cb => cb.value.toLowerCase());
    const cards = Array.from(dealsContainer.querySelectorAll('.card'));
    cards.forEach(card => {
      const cardCategory = card.getAttribute('data-category').toLowerCase();
      const cardDealType = card.getAttribute('data-deal-type').toLowerCase();
      const categoryMatch = selectedCategories.length === 0 || selectedCategories.includes(cardCategory);
      const dealTypeMatch = selectedDealTypes.length === 0 || selectedDealTypes.includes(cardDealType);
      card.style.display = (categoryMatch && dealTypeMatch) ? "" : "none";
    });
  }
});
