package com.example.debug

import com.example.Proposal

// Legitimate: a PREVIEW fixture, used only by @Preview code in src/debug.
fun fakeProposal(): Proposal = Proposal(action = "EXAMPLE action (preview fixture)")
