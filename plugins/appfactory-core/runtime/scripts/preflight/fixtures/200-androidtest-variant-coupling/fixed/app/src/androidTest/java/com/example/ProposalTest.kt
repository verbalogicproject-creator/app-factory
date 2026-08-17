package com.example

import org.junit.Test

class ProposalTest {
    @Test fun renders() {
        val p = exampleProposal()
        assert(p.action.isNotEmpty())
    }
}
