package com.example

import org.junit.Test

class ProposalTest {
    @Test fun renders() {
        val p = com.example.debug.fakeProposal()
        assert(p.action.isNotEmpty())
    }
}
