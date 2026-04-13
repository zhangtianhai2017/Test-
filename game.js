(() => {
    "use strict";

    // ── Constants ────────────────────────────────────────────────
    const SUITS = ["♠", "♥", "♦", "♣"];
    const RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
    const INITIAL_BALANCE = 1000;
    const DECK_COUNT = 6; // standard 6-deck shoe

    // ── State ────────────────────────────────────────────────────
    let deck = [];
    let dealerHand = [];
    let playerHand = [];
    let balance = INITIAL_BALANCE;
    let currentBet = 0;
    let gamePhase = "betting"; // betting | playing | done

    // ── DOM refs ─────────────────────────────────────────────────
    const $balance      = document.getElementById("balance");
    const $currentBet   = document.getElementById("current-bet");
    const $dealerCards  = document.getElementById("dealer-cards");
    const $playerCards  = document.getElementById("player-cards");
    const $dealerScore  = document.getElementById("dealer-score");
    const $playerScore  = document.getElementById("player-score");
    const $betControls  = document.getElementById("bet-controls");
    const $gameControls = document.getElementById("game-controls");
    const $dealBtn      = document.getElementById("deal-btn");
    const $hitBtn       = document.getElementById("hit-btn");
    const $standBtn     = document.getElementById("stand-btn");
    const $doubleBtn    = document.getElementById("double-btn");
    const $message      = document.getElementById("message");
    const $newRoundBtn  = document.getElementById("new-round-btn");
    const chipBtns      = document.querySelectorAll(".chip-btn");

    // ── Deck helpers ─────────────────────────────────────────────
    function createDeck() {
        const d = [];
        for (let i = 0; i < DECK_COUNT; i++) {
            for (const suit of SUITS) {
                for (const rank of RANKS) {
                    d.push({ suit, rank });
                }
            }
        }
        return d;
    }

    function shuffle(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    function drawCard() {
        if (deck.length < 20) {
            deck = shuffle(createDeck());
        }
        return deck.pop();
    }

    // ── Hand evaluation ──────────────────────────────────────────
    function cardValue(card) {
        if (card.rank === "A") return 11;
        if (["K", "Q", "J"].includes(card.rank)) return 10;
        return parseInt(card.rank, 10);
    }

    function handScore(hand) {
        let total = 0;
        let aces = 0;
        for (const card of hand) {
            total += cardValue(card);
            if (card.rank === "A") aces++;
        }
        while (total > 21 && aces > 0) {
            total -= 10;
            aces--;
        }
        return total;
    }

    function isBlackjack(hand) {
        return hand.length === 2 && handScore(hand) === 21;
    }

    // ── Rendering ────────────────────────────────────────────────
    function isRed(suit) {
        return suit === "♥" || suit === "♦";
    }

    function createCardElement(card, faceDown) {
        const el = document.createElement("div");
        el.classList.add("card", "deal-animation");

        if (faceDown) {
            el.classList.add("card-back");
        } else {
            el.classList.add("card-front");
            if (isRed(card.suit)) el.classList.add("red");
            el.innerHTML =
                `<span class="card-rank">${card.rank}</span>` +
                `<span class="card-suit">${card.suit}</span>`;
        }
        return el;
    }

    function renderHand(container, hand, hideFirst) {
        container.innerHTML = "";
        hand.forEach((card, i) => {
            const faceDown = hideFirst && i === 0;
            const el = createCardElement(card, faceDown);
            el.style.animationDelay = `${i * 0.12}s`;
            container.appendChild(el);
        });
    }

    function updateScores(hideDealer) {
        const ps = handScore(playerHand);
        $playerScore.textContent = ps;

        if (hideDealer) {
            $dealerScore.textContent = "?";
        } else {
            $dealerScore.textContent = handScore(dealerHand);
        }
    }

    function updateBalance() {
        $balance.textContent = balance;
        $currentBet.textContent = currentBet;
    }

    // ── Messages ─────────────────────────────────────────────────
    function showMessage(text, cls) {
        $message.textContent = text;
        $message.className = cls || "";
        $message.classList.remove("hidden");
    }

    function hideMessage() {
        $message.classList.add("hidden");
    }

    // ── UI state switches ────────────────────────────────────────
    function showBetting() {
        $betControls.classList.remove("hidden");
        $gameControls.classList.add("hidden");
        $newRoundBtn.classList.add("hidden");
        $dealBtn.disabled = currentBet === 0;
        chipBtns.forEach(btn => {
            btn.disabled = false;
        });
    }

    function showPlaying() {
        $betControls.classList.add("hidden");
        $gameControls.classList.remove("hidden");
        $newRoundBtn.classList.add("hidden");
        $doubleBtn.disabled = balance < currentBet || playerHand.length > 2;
    }

    function showDone() {
        $betControls.classList.add("hidden");
        $gameControls.classList.add("hidden");
        $newRoundBtn.classList.remove("hidden");
    }

    // ── Game flow ────────────────────────────────────────────────
    function placeBet(amount) {
        if (gamePhase !== "betting") return;
        if (amount > balance) return;
        balance -= amount;
        currentBet += amount;
        updateBalance();
        $dealBtn.disabled = false;
    }

    function deal() {
        if (currentBet === 0) return;
        gamePhase = "playing";
        hideMessage();

        // Reshuffle if needed
        if (deck.length < 20) {
            deck = shuffle(createDeck());
        }

        playerHand = [drawCard(), drawCard()];
        dealerHand = [drawCard(), drawCard()];

        renderHand($playerCards, playerHand, false);
        renderHand($dealerCards, dealerHand, true);
        updateScores(true);
        showPlaying();

        // Check for player blackjack
        if (isBlackjack(playerHand)) {
            revealDealer();
            if (isBlackjack(dealerHand)) {
                endRound("push");
            } else {
                endRound("blackjack");
            }
        }
    }

    function hit() {
        if (gamePhase !== "playing") return;
        playerHand.push(drawCard());
        renderHand($playerCards, playerHand, false);
        updateScores(true);

        // Disable double after first hit
        $doubleBtn.disabled = true;

        if (handScore(playerHand) > 21) {
            revealDealer();
            endRound("bust");
        }
    }

    function stand() {
        if (gamePhase !== "playing") return;
        revealDealer();
        dealerPlay();
    }

    function doubleDown() {
        if (gamePhase !== "playing") return;
        if (balance < currentBet) return;

        balance -= currentBet;
        currentBet *= 2;
        updateBalance();

        playerHand.push(drawCard());
        renderHand($playerCards, playerHand, false);
        updateScores(true);

        if (handScore(playerHand) > 21) {
            revealDealer();
            endRound("bust");
        } else {
            revealDealer();
            dealerPlay();
        }
    }

    function revealDealer() {
        renderHand($dealerCards, dealerHand, false);
        updateScores(false);
    }

    function dealerPlay() {
        const step = () => {
            const ds = handScore(dealerHand);
            if (ds < 17) {
                dealerHand.push(drawCard());
                renderHand($dealerCards, dealerHand, false);
                updateScores(false);
                setTimeout(step, 500);
            } else {
                determineWinner();
            }
        };
        setTimeout(step, 400);
    }

    function determineWinner() {
        const ps = handScore(playerHand);
        const ds = handScore(dealerHand);

        if (ds > 21) {
            endRound("win");
        } else if (ps > ds) {
            endRound("win");
        } else if (ds > ps) {
            endRound("lose");
        } else {
            endRound("push");
        }
    }

    function endRound(result) {
        gamePhase = "done";
        let msg = "";
        let cls = "";

        switch (result) {
            case "blackjack":
                msg = "Blackjack! 你赢了!";
                cls = "blackjack";
                balance += Math.floor(currentBet * 2.5); // 3:2 payout
                break;
            case "win":
                msg = "你赢了!";
                cls = "win";
                balance += currentBet * 2;
                break;
            case "bust":
                msg = "爆牌! 你输了!";
                cls = "lose";
                break;
            case "lose":
                msg = "庄家赢了!";
                cls = "lose";
                break;
            case "push":
                msg = "平局!";
                cls = "push";
                balance += currentBet;
                break;
        }

        currentBet = 0;
        updateBalance();
        showMessage(msg, cls);
        showDone();

        // Out of money
        if (balance <= 0) {
            setTimeout(() => {
                showMessage("筹码用完了! 重新开始...", "lose");
                setTimeout(() => {
                    balance = INITIAL_BALANCE;
                    updateBalance();
                    newRound();
                }, 2000);
            }, 1500);
        }
    }

    function newRound() {
        gamePhase = "betting";
        currentBet = 0;
        playerHand = [];
        dealerHand = [];
        $dealerCards.innerHTML = "";
        $playerCards.innerHTML = "";
        $dealerScore.textContent = "";
        $playerScore.textContent = "";
        updateBalance();
        hideMessage();
        showBetting();
    }

    // ── Event listeners ──────────────────────────────────────────
    chipBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const amount = parseInt(btn.dataset.amount, 10);
            placeBet(amount);
        });
    });

    $dealBtn.addEventListener("click", deal);
    $hitBtn.addEventListener("click", hit);
    $standBtn.addEventListener("click", stand);
    $doubleBtn.addEventListener("click", doubleDown);
    $newRoundBtn.addEventListener("click", newRound);

    // Keyboard shortcuts
    document.addEventListener("keydown", (e) => {
        if (gamePhase === "betting") {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                deal();
            }
        } else if (gamePhase === "playing") {
            if (e.key === "h" || e.key === "H") hit();
            if (e.key === "s" || e.key === "S") stand();
            if (e.key === "d" || e.key === "D") doubleDown();
        } else if (gamePhase === "done") {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                newRound();
            }
        }
    });

    // ── Init ─────────────────────────────────────────────────────
    deck = shuffle(createDeck());
    updateBalance();
    showBetting();
})();
